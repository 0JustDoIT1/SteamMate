import logging

from app.logging_config import SecretMaskingFilter, mask_secrets


def test_mask_key_query_param():
    url = "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/?key=ABCDEF123&steamid=1"
    masked = mask_secrets(url)
    assert "ABCDEF123" not in masked
    assert "key=***" in masked
    assert "steamid=1" in masked


def test_mask_explicit_secret_value():
    assert mask_secrets("token is s3cr3t-value", ("s3cr3t-value",)) == "token is ***"


def test_empty_secret_is_ignored():
    assert mask_secrets("nothing here", ("",)) == "nothing here"


def test_filter_masks_formatted_args(caplog):
    logger = logging.getLogger("test.masking")
    logger.addFilter(SecretMaskingFilter(("my-steam-key",)))
    with caplog.at_level(logging.INFO, logger="test.masking"):
        logger.info("GET %s", "https://x/?key=my-steam-key&a=1")
    assert "my-steam-key" not in caplog.text
    assert "key=***" in caplog.text
