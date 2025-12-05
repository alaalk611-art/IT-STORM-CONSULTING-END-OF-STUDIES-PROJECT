# test_logs.py — petit test indépendant

from src.automation.logs import append_log

print(">>> Avant append_log")
append_log({"test": "hello", "source": "test_logs.py"})
print(">>> Après append_log")
