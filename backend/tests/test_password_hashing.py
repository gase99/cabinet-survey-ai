from app.core.security import hash_password,verify_password
from passlib.hash import bcrypt


def test_new_hashes_do_not_truncate_unicode_or_long_password_suffixes():
    first='a'*80+'one'
    second='a'*80+'two'
    hashed=hash_password(first)
    assert hashed.startswith('$bcrypt-sha256$')
    assert verify_password(first,hashed)
    assert not verify_password(second,hashed)
    persian='پ'*60
    assert verify_password(persian,hash_password(persian))


def test_legacy_hashes_verify_without_destructive_migration():
    hashed=bcrypt.hash('FixturePass123!')
    assert verify_password('FixturePass123!',hashed)
    assert not verify_password('wrong',hashed)
    assert not verify_password('anything','not-a-valid-hash')
