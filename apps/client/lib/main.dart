import 'package:flutter/material.dart';

void main() {
  runApp(const CabinetSurveyApp());
}

class CabinetSurveyApp extends StatelessWidget {
  const CabinetSurveyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Cabinet Survey AI',
      theme: ThemeData(colorSchemeSeed: const Color(0xFF536B78), useMaterial3: true),
      home: const Scaffold(
        body: Center(child: Text('Cabinet Survey AI — foundation scaffold')),
      ),
    );
  }
}
