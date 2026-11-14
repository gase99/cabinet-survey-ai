package com.cabinetsurvey.client

import android.app.Activity
import android.content.Intent
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    private var pending: MethodChannel.Result? = null
    private var document: ByteArray? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, CHANNEL)
            .setMethodCallHandler { call, result ->
                if (call.method != "saveDocument") {
                    result.notImplemented()
                    return@setMethodCallHandler
                }
                if (pending != null) {
                    result.error("BUSY", "Another document selection is open", null)
                    return@setMethodCallHandler
                }
                val name = call.argument<String>("name")
                val bytes = call.argument<ByteArray>("bytes")
                val mime = call.argument<String>("mime")
                if (!DocumentRules.valid(name, bytes, mime)) {
                    result.error("INVALID_DOCUMENT", "Invalid filename, type or size", null)
                    return@setMethodCallHandler
                }
                pending = result
                document = bytes!!
                try {
                    val intent = Intent(Intent.ACTION_CREATE_DOCUMENT).apply {
                        addCategory(Intent.CATEGORY_OPENABLE)
                        type = mime
                        putExtra(Intent.EXTRA_TITLE, name)
                    }
                    startActivityForResult(intent, SAVE_REQUEST)
                } catch (error: Exception) {
                    finish(null, "SAVE_FAILED", "No document picker is available")
                }
            }
    }

    @Deprecated("Android framework callback retained for FlutterActivity embedding")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != SAVE_REQUEST) return
        if (resultCode != Activity.RESULT_OK) {
            finish(false, null, null)
            return
        }
        val uri = data?.data
        if (uri == null) {
            finish(null, "SAVE_FAILED", "No destination was returned")
            return
        }
        try {
            val output = contentResolver.openOutputStream(uri, "wt")
                ?: throw IllegalStateException("Destination is not writable")
            output.use { it.write(document ?: throw IllegalStateException("Document missing")) }
            finish(true, null, null)
        } catch (error: Exception) {
            finish(null, "SAVE_FAILED", "Could not write the selected document")
        }
    }

    private fun finish(value: Boolean?, code: String?, message: String?) {
        val result = pending
        pending = null
        document = null
        if (code == null) result?.success(value) else result?.error(code, message, null)
    }

    override fun onDestroy() {
        finish(null, "CANCELLED", "Document selection was interrupted")
        super.onDestroy()
    }

    companion object {
        const val CHANNEL = "com.cabinetsurvey.client/documents"
        const val SAVE_REQUEST = 4310
    }
}
