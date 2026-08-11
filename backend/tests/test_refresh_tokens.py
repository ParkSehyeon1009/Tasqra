from app.core.security import create_refresh_token, hash_refresh_token


def test_refresh_token_is_random_and_only_hash_is_persistable():
    first_raw, first_hash = create_refresh_token()
    second_raw, second_hash = create_refresh_token()
    assert first_raw != second_raw
    assert first_hash != second_hash
    assert first_hash == hash_refresh_token(first_raw)
    assert first_raw != first_hash
    assert len(first_hash) == 64
