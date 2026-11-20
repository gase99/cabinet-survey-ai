package com.cabinetsurvey.client

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class DocumentRulesTest {
    private val bytes = byteArrayOf(37, 80, 68, 70)
    @Test fun acceptsPdfAndPng() {
        assertTrue(DocumentRules.valid("survey.pdf", bytes, "application/pdf"))
        assertTrue(DocumentRules.valid("survey.png", bytes, "image/png"))
    }
    @Test fun rejectsTraversalEmptyAndUnsupportedDocuments() {
        for (name in listOf(null, "", "../survey.pdf", "folder/survey.pdf", "folder\\survey.pdf"))
            assertFalse(DocumentRules.valid(name, bytes, "application/pdf"))
        assertFalse(DocumentRules.valid("survey.pdf", ByteArray(0), "application/pdf"))
        assertFalse(DocumentRules.valid("survey.pdf", null, "application/pdf"))
        assertFalse(DocumentRules.valid("survey.html", bytes, "text/html"))
        assertFalse(DocumentRules.valid("survey.pdf", ByteArray(DocumentRules.MAX_BYTES + 1), "application/pdf"))
    }
}
