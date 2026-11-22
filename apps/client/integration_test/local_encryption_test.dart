import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:sqflite/sqflite.dart' as plain;
import 'package:sqflite_sqlcipher/sqflite.dart' as cipher;
import 'package:image_picker/image_picker.dart';
import 'package:cabinet_survey_ai/services/photo_importer.dart';
import 'package:cabinet_survey_ai/core/store.dart';
import 'package:cabinet_survey_ai/core/secure_database.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  testWidgets('picker cache files are removed on success, failure and cancellation', (tester) async {
    final cache = (await SecureDatabase.channel.invokeMethod<String>('pickerCachePath'))!;
    for (final scenario in ['success', 'cancel', 'picker-error', 'save-error']) {
      final file = File('$cache/picker-fixture-$scenario.jpg');
      await file.writeAsBytes([1, 2, 3]);
      final importer = PhotoImporter(pick: (_) async {
        if (scenario == 'picker-error') throw StateError('picker failed');
        return scenario == 'cancel' ? null : XFile(file.path);
      });
      Future<void> capture() => importer.capture(ImageSource.gallery, (_, bytes) async {
        expect(bytes, [1, 2, 3]);
        if (scenario == 'save-error') throw StateError('save failed');
      });
      if (scenario.endsWith('error')) {
        await expectLater(capture(), throwsStateError);
      } else {
        await capture();
      }
      expect(await file.exists(), false, reason: scenario);
    }
  });
  testWidgets('legacy warning, encrypted storage, wrong key and reset', (tester) async {
    final dir = await plain.getDatabasesPath();
    final old = '$dir/${SecureDatabase.oldName}';
    final encrypted = '$dir/${SecureDatabase.newName}';
    // Disposable integration-test installation only.
    await SecureDatabase.resetAfterConsent();
    await SecureDatabase.markResynced(encrypted);
    final legacy = await LocalStore.open(testFactory: plain.databaseFactory, path: old);
    final store = LocalStore(legacy, 'device-local');
    await store.save('project', {'id':'p', 'title':'legacy', 'status':'draft'});
    await store.photo('p', 'legacy.png', Uint8List.fromList([1, 2, 3]));
    await legacy.close();
    try {
      await SecureDatabase.open();
      fail('legacy database must require explicit reset');
    } on LocalResetRequired catch (warning) {
      expect(warning.pending, 1);
      expect(warning.photos, 1);
      expect(warning.localRecords, 1);
      expect(warning.invalidKey, false);
    }
    for (final suffix in ['-wal', '-shm', '-journal']) {
      await File('$old$suffix').writeAsString('legacy fixture');
    }
    await SecureDatabase.resetAfterConsent();
    for (final suffix in ['', '-wal', '-shm', '-journal']) {
      expect(await File('$old$suffix').exists(), false);
    }
    var db = await SecureDatabase.open();
    expect(await SecureDatabase.needsResync(db.path), true);
    final encryptedStore = LocalStore(db, 'device-local');
    const secret = 'fixture-private-content-never-plaintext';
    await encryptedStore.save('project', {'id':'p2', 'title':secret, 'status':'draft'});
    await encryptedStore.photo('p2', 'fixture.png', Uint8List.fromList(utf8.encode(secret)));
    await db.close();
    final raw = await File(encrypted).readAsBytes();
    expect(ascii.decode(raw.take(16).toList(), allowInvalid: true), isNot('SQLite format 3\u0000'));
    expect(latin1.decode(raw), isNot(contains(secret)));
    await expectLater(cipher.openDatabase(encrypted, password:'incorrect', singleInstance:false), throwsA(anything));
    db = await SecureDatabase.open();
    expect((await LocalStore(db, 'device-local').get('p2'))!['title'], secret);
    expect((await LocalStore(db, 'device-local').photos('p2')).length, 1);
    await db.close();
    // Loss of the wrapped key is detected without trying to use an unencrypted database,
    // and is one of the cases where reset is offered immediately.
    await SecureDatabase.channel.invokeMethod<void>('resetKey');
    await expectLater(SecureDatabase.open(), throwsA(isA<LocalResetRequired>()));
    // Replace the missing key with a different valid wrapping/password pair; SQLCipher
    // must reject it and the app must offer recovery, not crash. On the API-35 emulator
    // SQLCipher reports a generic `open_failed`, which is retry-first (LocalOpenFailed);
    // builds reporting "not a database" go straight to reset.
    await SecureDatabase.channel.invokeMethod<String>('databasePassword', {'create': true});
    await expectLater(SecureDatabase.open(), throwsA(anyOf(isA<LocalOpenFailed>(), isA<LocalResetRequired>())));
    await SecureDatabase.resetAfterConsent();
    db = await SecureDatabase.open();
    expect(await SecureDatabase.needsResync(db.path), true);
    expect(await LocalStore(db, 'device-local').list('project'), isEmpty);
    await db.close();
    await SecureDatabase.resetAfterConsent();
    await SecureDatabase.markResynced(encrypted);
  });
}
