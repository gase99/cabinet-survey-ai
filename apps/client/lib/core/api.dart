import 'dart:convert';
import 'dart:typed_data';
import 'package:http/http.dart' as http;
import '../domain/survey.dart';

class ApiException implements Exception {
  final int status;
  final String message;
  ApiException(this.status, this.message);
  @override
  String toString() => message;
}

class Api {
  final http.Client client;
  final Uri base;
  String? token;
  Api({http.Client? client, String baseUrl = const String.fromEnvironment(
    'API_BASE_URL', defaultValue: '/api/v1/')})
      : client = client ?? http.Client(), base = Uri.base.resolve(baseUrl);

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
  void close() => client.close();
}
