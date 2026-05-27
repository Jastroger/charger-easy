# Manual current test

The compatibility entry point still works:

```bash
sudo python3 test/set-cc.py
```

Preferred direct command:

```bash
sudo python3 -m charger_easy.tools.set_current 6
```

Use `--eeprom` only when you intentionally want to write the MCP4161 EEPROM register `0x20`.
The default writes the volatile RAM register `0x00`.

Automated tests do not need Raspberry Pi hardware:

```bash
python -m unittest discover -s tests
python -m pytest
```
