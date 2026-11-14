import 'dart:convert';
import 'dart:typed_data';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';
import '../domain/survey.dart';

class ApiException implements Exception {
  final int status;
  final String message;
  ApiException(this.status, this.message);
  @override
  String toString() => message;
}

/// Android has no same-origin document URL. Release builds require an explicit
/// HTTPS endpoint; emulator HTTP is restricted to debug/profile development.
Uri validateApiBase(String value, {required bool release}) {
  final uri = Uri.tryParse(value.trim());
  if (uri == null || !uri.hasAuthority || uri.host.isEmpty ||
      !{'http', 'https'}.contains(uri.scheme) || uri.userInfo.isNotEmpty ||
      uri.hasQuery || uri.hasFragment || (release && uri.scheme != 'https')) {
    throw ArgumentError('Set API_BASE_URL to an absolute HTTPS API URL ending in /api/v1/');
  }
  if (!uri.path.endsWith('/api/v1/')) {
    throw ArgumentError('API_BASE_URL must end in /api/v1/');
  }
  return uri;
}

class Api {
  final http.Client client;
  final Uri base;
  String? token;
  Api({http.Client? client, String? baseUrl})
      : client = client ?? http.Client(),
        base = validateApiBase(baseUrl ?? const String.fromEnvironment('API_BASE_URL',
            defaultValue: 'http://10.0.2.2:8000/api/v1/'), release: kReleaseMode);

  Future<http.Response> _send(String method, String path, Json? body) async {
    final request = http.Request(method, base.resolve(path));
    request.headers['Content-Type'] = 'application/json';
    if (token != null) request.headers['Authorization'] = 'Bearer $token';
    if (body != null) request.body = jsonEncode(body);
    final response = await http.Response.fromStream(
      await client.send(request).timeout(const Duration(seconds: 30)));
    if (response.statusCode < 200 || response.statusCode >= 300) {
      String message = 'HTTP ${response.statusCode}';
      try { message = '${(jsonDecode(response.body) as Json)['detail']}'; } catch (_) {}
      throw ApiException(response.statusCode, message);
    }
    return response;
  }
  Future<dynamic> request(String method, String path, [Json? body]) async {
    final response = await _send(method, path, body);
    return response.body.isEmpty ? null : jsonDecode(utf8.decode(response.bodyBytes));
  }
  Future<Uint8List> bytes(String path) async => (await _send('GET', path, null)).bodyBytes;
  Future<Json> sketch(Uint8List bytes, String filename) async {
    final mime = bytes.length >= 8 && bytes[0] == 137 && bytes[1] == 80
      ? 'image/png' : bytes.length >= 3 && bytes[0] == 255 && bytes[1] == 216
        ? 'image/jpeg' : 'image/webp';
    final request = http.MultipartRequest('POST', base.resolve('ai/sketch-analysis'));
    if (token != null) request.headers['Authorization'] = 'Bearer $token';
    request.files.add(http.MultipartFile.fromBytes('file', bytes, filename: filename, contentType: MediaType.parse(mime)));
    final response = await http.Response.fromStream(await client.send(request).timeout(const Duration(seconds: 90)));
    if (response.statusCode != 200) {
      String message = 'HTTP ${response.statusCode}';
      try { message = '${(jsonDecode(response.body) as Json)['detail']}'; } catch (_) {}
      throw ApiException(response.statusCode, message);
    }
    return jsonDecode(utf8.decode(response.bodyBytes)) as Json;
  }
  void close() => client.close();
}
