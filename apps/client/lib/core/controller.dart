import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:sqflite/sqflite.dart';
import '../domain/survey.dart';
import 'api.dart';
import 'store.dart';

final databaseProvider = FutureProvider<Database>((ref) => LocalStore.open());
final controllerProvider = ChangeNotifierProvider.family<SurveyController, Database>(
  (ref, db) {
    final controller = SurveyController(db);
    ref.onDispose(controller.api.close);
    return controller;
  });

class SurveyController extends ChangeNotifier {
  final Database db;
  final Api api;
  final FlutterSecureStorage secure = const FlutterSecureStorage(aOptions: AndroidOptions(encryptedSharedPreferences: true));
  String owner = 'device-local';
  bool offline = false;
  String? email;
  SurveyController(this.db, {Api? api}) : api = api ?? Api();
  LocalStore get store => LocalStore(db, owner);

  Future<void> login(String address, String password, {String? name}) async {
    if (name != null) await api.request('POST', 'auth/register', {
      'email': address, 'password': password, 'display_name': name});
    final tokens = await api.request('POST', 'auth/login', {'email':address, 'password':password}) as Json;
    api.token = tokens['access_token'] as String;
    try {
      final me = await api.request('GET','auth/me') as Json;
      owner = me['id'] as String;
      email = address;
      // Refresh token stays in Android secure storage, never in the survey database.
      await secure.write(key: 'refresh', value: tokens['refresh_token'] as String);
      await secure.write(key: 'owner', value: owner);
      await secure.write(key: 'email', value: address);
      offline = false;
      notifyListeners();
    } catch (_) { api.token = null; rethrow; }
  }
  Future<void> restore() async {
    try {
      final refresh=await secure.read(key:'refresh');
      final savedOwner=await secure.read(key:'owner');
      if(refresh==null || savedOwner==null) return;
      owner=savedOwner;
      email=await secure.read(key:'email');
      offline=true;
      try {
        final tokens=await api.request('POST','auth/refresh',{'refresh_token':refresh}) as Json;
        api.token=tokens['access_token'] as String;
        await secure.write(key:'refresh',value:tokens['refresh_token'] as String);
        offline=false;
      } on ApiException catch(error) {
        if(error.status==401) { await logout(); return; }
      } catch(_) { /* Network absent: retain account-scoped local capture. */ }
      notifyListeners();
    } catch(_) { /* Secure storage unavailable: use explicit sign-in/offline workspace. */ }
  }
  void captureOffline() { offline = true; notifyListeners(); }
  Future<void> logout() async {
    try {
      if(api.token!=null) await api.request('POST','auth/logout',{});
    } catch(_) { /* Offline logout clears local credentials; remote revocation requires connectivity. */ }
    for(final key in ['refresh','owner','email']) { await secure.delete(key:key); }
    api.token = null;
    owner = 'device-local'; email = null; offline = false;
    notifyListeners();
  }

  /// Stop an entity's dependent operations at the first conflict or failed write.
  /// Network failures leave the durable operation pending, using the same ID on retry.
  Future<void> sync() async {
    if (api.token == null) throw StateError('Sign in to synchronize this account');
    final blocked = <String>{};
    for (final row in await store.queue()) {
      final op = row['operation'] as Json;
      final entity = op['entity_id'] as String;
      if (row['state'] == 'conflict' || row['state'] == 'failed') blocked.add(entity);
      if (row['state'] != 'pending' || blocked.contains(entity)) continue;
      final reply = await api.request('POST', 'sync/push', {'operations': [op]}) as Json;
      final result = (reply['results'] as List).single as Json;
      await store.result(op['id'] as String, result);
      if (result['status'] != 'applied') blocked.add(entity);
    }
    final dirty = (await store.queue()).where((r) => r['state'] != 'applied' && r['state'] != 'resolved')
      .map((r) => (r['operation'] as Json)['entity_id']).toSet();
    for (var page = 1;; page++) {
      final customers = await api.request('GET','customers?page=$page&page_size=100') as List;
      for (final raw in customers) {
        final customer = raw as Json;
        if (!dirty.contains(customer['id'])) await store.cache('customer', customer);
      }
      if (customers.length < 100) break;
    }
    // Import all pages. Never replace records with unacknowledged local edits.
    for (var page = 1;; page++) {
      final projects = await api.request('GET','projects?page=$page&page_size=100') as List;
      for (final raw in projects) {
        final p = raw as Json;
        if (!dirty.contains(p['id'])) await store.cache('project', p);
        final rooms = await api.request('GET', 'projects/${p['id']}/rooms') as List;
        for (final rawRoom in rooms) {
          final r = rawRoom as Json;
          if (!dirty.contains(r['id'])) await store.cache('room',r);
          final walls = await api.request('GET', 'rooms/${r['id']}/walls') as List;
          for (final rawWall in walls) {
            final w = rawWall as Json;
            if (!dirty.contains(w['id'])) await store.cache('wall',w);
            final elements = await api.request('GET', 'walls/${w['id']}/elements') as List;
            for (final rawElement in elements) {
              final e = rawElement as Json;
              if (!dirty.contains(e['id'])) await store.cache('element',e);
            }
          }
        }
      }
      if (projects.length < 100) break;
    }
    notifyListeners();
  }
}
