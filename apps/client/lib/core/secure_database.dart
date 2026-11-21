import 'dart:io';
import 'package:flutter/services.dart';
import 'package:sqflite/sqflite.dart' as plain;
import 'package:sqflite_sqlcipher/sqflite.dart' as cipher;
import 'store.dart';

/// Destructive recovery is never performed until the owner explicitly consents.
class LocalResetRequired implements Exception {
  final int? pending;
  final int? photos;
  final int? localRecords;
  final bool invalidKey;
  const LocalResetRequired({this.pending, this.photos, this.localRecords, this.invalidKey = false});
}

class SecureDatabase {
  static const channel = MethodChannel('com.cabinetsurvey.client/local_security');
  static const oldName = 'cabinet_survey.sqlite';
  static const newName = 'cabinet_survey_encrypted.sqlite';
  static Future<String> get _directory async => plain.getDatabasesPath();
  static Future<String> _path(String name) async => '${await _directory}/$name';
  static String _marker(String path) => '$path.resync-required';

  static Future<bool> needsResync(String path) => File(_marker(path)).exists();
  static Future<void> markResynced(String path) async {
    final marker = File(_marker(path));
    if (await marker.exists()) await marker.delete();
  }

  static Future<LocalResetRequired> _legacyWarning(String path) async {
    plain.Database? db;
    try {
      db = await plain.openDatabase(path, readOnly: true, singleInstance: false);
      final pending = plain.Sqflite.firstIntValue(await db.rawQuery(
        "SELECT COUNT(*) FROM outbox WHERE state NOT IN ('applied','resolved')"));
      final photos = plain.Sqflite.firstIntValue(await db.rawQuery('SELECT COUNT(*) FROM photos'));
      final local = plain.Sqflite.firstIntValue(await db.rawQuery("SELECT COUNT(*) FROM records WHERE owner = 'device-local'"));
      return LocalResetRequired(pending: pending, photos: photos, localRecords: local);
    } catch (_) {
      // An unreadable legacy database must not be silently deleted.
      return const LocalResetRequired();
    } finally {
      await db?.close();
    }
  }

  static Future<plain.Database> open() async {
    await channel.invokeMethod<void>('clearPickerCache');
    final legacy = await _path(oldName);
    if (await File(legacy).exists()) throw await _legacyWarning(legacy);
    final path = await _path(newName);
    final exists = await File(path).exists();
    final String password;
    try {
      password = (await channel.invokeMethod<String>('databasePassword', {'create': !exists}))!;
    } on PlatformException {
      if (exists) throw const LocalResetRequired(invalidKey: true);
      rethrow;
    }
    try {
      final db = await cipher.openDatabase(path, password: password, version: 1,
          onConfigure: LocalStore.configure, onCreate: LocalStore.create);
      final version = await db.rawQuery('PRAGMA cipher_version');
      if (version.isEmpty || version.first.values.first.toString().isEmpty) {
        await db.close();
        throw StateError('SQLCipher is unavailable; database was not opened');
      }
      return db;
    } on plain.DatabaseException catch (error) {
      final text = error.toString().toLowerCase();
      if (exists && (text.contains('not a database') || text.contains('file is encrypted') || text.contains('open_failed'))) {
        throw const LocalResetRequired(invalidKey: true);
      }
      rethrow;
    }
  }

  static Future<void> resetAfterConsent() async {
    final encrypted = await _path(newName);
    // The marker survives process restarts until a full server sync succeeds.
    await File(_marker(encrypted)).writeAsString('required', flush: true);
    for (final name in [oldName, newName]) {
      final path = await _path(name);
      for (final suffix in ['', '-wal', '-shm', '-journal']) {
        final file = File('$path$suffix');
        if (await file.exists()) await file.delete();
      }
    }
    await channel.invokeMethod<void>('resetKey');
  }
}
