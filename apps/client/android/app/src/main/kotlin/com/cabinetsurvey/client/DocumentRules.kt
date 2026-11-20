package com.cabinetsurvey.client

/** Mirrors the Dart boundary; native code must also validate untrusted channel input. */
object DocumentRules {
    const val MAX_BYTES = 32 * 1024 * 1024
    fun valid(name: String?, bytes: ByteArray?, mime: String?): Boolean =
        !name.isNullOrBlank() && !name.contains('/') && !name.contains('\\') &&
        bytes != null && bytes.isNotEmpty() && bytes.size <= MAX_BYTES &&
        mime in setOf("application/pdf", "image/png")
}
