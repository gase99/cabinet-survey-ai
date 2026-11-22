package com.cabinetsurvey.client

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.AtomicFile
import android.util.Base64
import java.io.File
import java.security.KeyStore
import java.security.SecureRandom
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** The wrapped database password or its Keystore wrapping key no longer exists. Only this
 * case (and SQLCipher "not a database"/"file is encrypted") is reported as needing reset;
 * every other failure is surfaced as retryable first. */
class WrappedKeyMissingException(message: String) : IllegalStateException(message)

/** The random database password is encrypted by a non-exportable Android Keystore key.
 * Only the IV and ciphertext are persisted, in app-private no-backup storage. */
class LocalSecurity(private val context: Context) {
    private val alias = "cabinet-survey-db-wrap-v1"
    private val wrappedFile get() = AtomicFile(File(context.noBackupFilesDir, "db-key-v1"))
    private fun keyStore() = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }

    @Synchronized
    fun databasePassword(create: Boolean): String {
        val store = keyStore()
        val file = wrappedFile
        if (file.baseFile.exists()) {
            val wrappingKey = store.getKey(alias, null) as? SecretKey
                ?: throw WrappedKeyMissingException("Keystore key unavailable")
            val bytes = file.readFully()
            require(bytes.size >= 12 + 16) { "Invalid wrapped key" }
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.DECRYPT_MODE, wrappingKey, GCMParameterSpec(128, bytes.copyOfRange(0, 12)))
            return Base64.encodeToString(cipher.doFinal(bytes.copyOfRange(12, bytes.size)), Base64.NO_WRAP)
        }
        if (!create) throw WrappedKeyMissingException("Wrapped database key unavailable")
        val wrappingKey = (store.getKey(alias, null) as? SecretKey) ?: KeyGenerator.getInstance(
            KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore"
        ).run {
            init(KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).setKeySize(256).build())
            generateKey()
        }
        val password = ByteArray(32).also { SecureRandom().nextBytes(it) }
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, wrappingKey)
        val output = file.startWrite()
        try {
            output.write(cipher.iv + cipher.doFinal(password))
            file.finishWrite(output)
        } catch (error: Exception) {
            file.failWrite(output)
            throw error
        }
        return Base64.encodeToString(password, Base64.NO_WRAP)
    }

    @Synchronized
    fun resetKey() {
        wrappedFile.delete()
        keyStore().deleteEntry(alias)
    }

    fun clearPickerCache() {
        // image_picker puts camera originals, copied gallery images and resized files
        // under this app-private cache. Never delete a URI/source outside this directory.
        val files = context.cacheDir.listFiles() ?: throw IllegalStateException("Cache unavailable")
        files.forEach { child ->
            check(child.deleteRecursively()) { "Could not clear temporary files" }
        }
    }
}
