import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'core/controller.dart';
import 'features/workspace.dart';

void main() { WidgetsFlutterBinding.ensureInitialized(); runApp(const ProviderScope(child: CabinetSurveyApp())); }

class CabinetSurveyApp extends StatefulWidget {
  const CabinetSurveyApp({super.key});
  @override
  State<CabinetSurveyApp> createState() => _CabinetSurveyAppState();
}
class _CabinetSurveyAppState extends State<CabinetSurveyApp> {
  Locale locale = const Locale('fa');
  @override
  Widget build(BuildContext context) => MaterialApp(
    title:'Cabinet Survey AI', debugShowCheckedModeBanner:false,
    locale:locale, supportedLocales: const [Locale('fa'),Locale('en')],
    localizationsDelegates: GlobalMaterialLocalizations.delegates,
    theme:ThemeData(colorSchemeSeed: const Color(0xff256c67), useMaterial3:true),
    darkTheme:ThemeData(colorSchemeSeed: const Color(0xff256c67), brightness:Brightness.dark, useMaterial3:true),
    home: Bootstrap(toggleLocale: () => setState(() => locale = Locale(locale.languageCode == 'fa' ? 'en' : 'fa'))));
}
class Bootstrap extends ConsumerWidget {
  final VoidCallback toggleLocale;
  const Bootstrap({super.key, required this.toggleLocale});
  @override
  Widget build(BuildContext context, WidgetRef ref) => ref.watch(databaseProvider).when(
    data:(db) => Workspace(controller:ref.watch(controllerProvider(db)), toggleLocale:toggleLocale),
    loading:() => const Scaffold(body:Center(child:CircularProgressIndicator())),
    error:(error,stack) => Scaffold(body:Center(child:SelectableText('Local database unavailable: $error'))));
}
