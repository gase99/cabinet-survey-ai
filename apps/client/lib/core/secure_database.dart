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

/// A generic open failure (for example SQLCipher `open_failed`, or a transient Keystore
/// error). The UI must offer "try again" before any destructive reset is shown.
class LocalOpenFailed implements Exception {
  const LocalOpenFailed();
}

/// Classifies storage-open failures. Only "not a database", "file is encrypted" and a
/// missing wrapped key are reset-immediately; anything else on an existing database is
/// retryable first. Returns null when the error must be rethrown unchanged.
class OpenFailureClassifier {
  static const wrappedKeyMissing = 'WRAPPED_KEY_MISSING';

  static Exception? database(String message, {required bool exists}) {
    if (!exists) return null;
    final text = message.toLowerCase();
    if (text.contains('not a database') || text.contains('file is encrypted')) {
      return const LocalResetRequired(invalidKey: true);
    }
    if (text.contains('open_failed')) return const LocalOpenFailed();
    return null;
  }

  static Exception? key(PlatformException error, {required bool exists}) {
    if (!exists) return null;
    if (error.code == wrappedKeyMissing) return const LocalResetRequired(invalidKey: true);
    return const LocalOpenFailed();
  }
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
    } on PlatformException catch (error) {
      final classified = OpenFailureClassifier.key(error, exists: exists);
      if (classified != null) throw classified;
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
      final classified = OpenFailureClassifier.database(error.toString(), exists: exists);
      if (classified != null) throw classified;
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
