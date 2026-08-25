## Manual login bug fix

The previous `run.py login` path assumed `NAVER_ID` and `NAVER_PW` were always present. When either value was missing, `human_type()` received `None` and raised `TypeError`, which immediately closed the browser in the `finally` block.

`manual_login.py` provides a safe desktop login path that:

- always launches a visible browser;
- ignores `HEADLESS=1`;
- does not require storing Naver ID/password in `.env`;
- waits for the user to complete login, 2FA, or captcha manually;
- saves `storage_state.json` only after a successful redirect.
