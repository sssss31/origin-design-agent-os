def test_nat64_addresses_follow_their_embedded_ipv4() -> None:
    from app.core.ssrf import _is_public

    assert _is_public("64:ff9b::2cdb:96d7")  # 44.219.150.215 (public)
    assert not _is_public("64:ff9b::7f00:1")  # 127.0.0.1 (loopback)
    assert not _is_public("64:ff9b::a9fe:a9fe")  # 169.254.169.254 (metadata)
