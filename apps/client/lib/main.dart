import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'core/controller.dart';
import 'core/secure_database.dart';
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
    error:(error,stack) {
      void reset() { ref.read(openRetryCountProvider.notifier).state = 0; ref.invalidate(databaseProvider); }
      void retry() { ref.read(openRetryCountProvider.notifier).state++; ref.invalidate(databaseProvider); }
      if (error is LocalResetRequired) return LocalResetScreen(warning:error, onReset:reset);
      if (error is LocalOpenFailed) {
        // A generic open failure may be transient: the destructive reset is offered only
        // after at least one explicit retry has also failed.
        return ref.watch(openRetryCountProvider) == 0
          ? LocalOpenFailedScreen(onRetry:retry)
          : LocalResetScreen(warning:const LocalResetRequired(invalidKey:true), onReset:reset, onRetry:retry);
      }
      return const Scaffold(body:Center(child:SelectableText('Local database unavailable. Restart the app or seek assistance. / پایگاه داده در دسترس نیست.')));
    });
}

/// Number of explicit "try again" attempts after a generic local-database open failure.
final openRetryCountProvider = StateProvider<int>((ref) => 0);

class LocalOpenFailedScreen extends StatelessWidget {
  final VoidCallback onRetry;
  const LocalOpenFailedScreen({super.key, required this.onRetry});
  @override
  Widget build(BuildContext context) => Scaffold(body:Center(child:SingleChildScrollView(padding:const EdgeInsets.all(24),
    child:Column(mainAxisSize:MainAxisSize.min, children:[
      Text('Local database could not be opened / پایگاه داده محلی باز نشد', style:Theme.of(context).textTheme.titleLarge),
      const Text('This may be temporary. No data has been deleted. Try again.\n'
        'ممکن است موقتی باشد. هیچ داده‌ای حذف نشده است. دوباره تلاش کنید.'),
      FilledButton(onPressed:onRetry, child:const Text('Try again / تلاش دوباره')),
    ]))));
}

class LocalResetScreen extends StatefulWidget {
  final LocalResetRequired warning;
  final VoidCallback onReset;
  /// When set, retrying is shown before the destructive reset (generic open failures).
  final VoidCallback? onRetry;
  const LocalResetScreen({super.key, required this.warning, required this.onReset, this.onRetry});
  @override
  State<LocalResetScreen> createState() => _LocalResetScreenState();
}
class _LocalResetScreenState extends State<LocalResetScreen> {
  bool busy = false;
  String? error;
  @override
  Widget build(BuildContext context) {
    final warning = widget.warning;
    String count(int? value) => value?.toString() ?? 'unknown / نامشخص';
    return Scaffold(body:Center(child:SingleChildScrollView(padding:const EdgeInsets.all(24),
      child:Column(mainAxisSize:MainAxisSize.min, children:[
        Text(warning.invalidKey ? 'Local database key or file unavailable / کلید یا پایگاه داده محلی در دسترس نیست' :
          'Old unencrypted database found / پایگاه داده رمزگذاری‌نشده یافت شد', style:Theme.of(context).textTheme.titleLarge),
        if (!warning.invalidKey) Text('Unsynced or conflicted operations / عملیات همگام‌نشده: ${count(warning.pending)}\n'
          'Local-only records / داده‌های محلی: ${count(warning.localRecords)}\n'
          'Stored photos / عکس‌های ذخیره‌شده: ${count(warning.photos)}'),
        const Text('Deleting local data is permanent. Unsynced changes, device-local records and photos cannot be recovered from the server. '
          'Only data already on the server can be re-synced after signing in.\n'
          'حذف داده‌های محلی دائمی است. تغییرات همگام‌نشده، داده‌های محلی و عکس‌ها قابل بازیابی از سرور نیستند.'),
        if (error != null) Text(error!),
        if (widget.onRetry != null) ...[
          const Text('Trying again did not open the database. / تلاش دوباره پایگاه داده را باز نکرد.'),
          FilledButton(onPressed:busy ? null : widget.onRetry, child:const Text('Try again / تلاش دوباره')),
        ],
        FilledButton(onPressed:busy ? null : () async {
          final yes = await showDialog<bool>(context:context,builder:(dialog) => AlertDialog(
            title:const Text('Delete local data? / حذف داده‌های محلی؟'),
            content:const Text('This cannot be undone. / این عملیات برگشت‌پذیر نیست.'),
            actions:[TextButton(onPressed:() => Navigator.pop(dialog,false), child:const Text('Cancel / انصراف')),
              FilledButton(onPressed:() => Navigator.pop(dialog,true), child:const Text('Delete / حذف'))]));
          if (yes != true || !context.mounted) return;
          setState(() { busy=true; error=null; });
          try { await SecureDatabase.resetAfterConsent(); widget.onReset(); }
          catch (_) { if (mounted) setState(() => error='Reset failed; local data may remain. Retry. / حذف ناموفق بود. دوباره تلاش کنید.'); }
          finally { if (mounted) setState(() => busy=false); }
        },child:const Text('Reset and re-sync / حذف و همگام‌سازی مجدد')),
      ]))));
  }

}
