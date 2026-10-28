# 预交付本地检查（仅代表无需凭据的部分）

环境：容器中 Python 3.13 / pytest；未连接 MiniMax API、seekdb、PowerContext Server。以下是**实际执行**结果，不构成线上技术接入验收：

1. `python -m pytest -q tests/test_sddflow_unit.py tests/test_sql_mock_unit.py tests/test_clients_mock_unit.py tests/test_regression.py`：**14 passed**。
2. `python -m pytest -q tests/test_feature_min_stock.py`（基线版本）：**4 failed**；4 个目标测试均因库存条件未实现导致断言失败（含 min_stock=0/backorder 边界）。
3. `bash scripts/verify_local_no_services.sh`：退出码 **0**（兼容/辅助测试通过，目标断言失败符合预期）。
4. 在临时副本中使用**明确标记的模拟响应**对 `model_apply -> after tests -> reproduce_offline -> reset-code` 的程序路径做了开发自测：修改后目标/回归测试均退出码 0。**模拟响应没有写入此项目的 evidence/，也不能作为 MiniMax 实际参与的证明**。

正式提交前还必须运行 `bash scripts/full_demo_wsl.sh` 产生真实数据库、MiniMax 和 PowerContext 记录，并通过 `bash scripts/check_ready_to_commit.sh`。此文件可用于告知审阅者什么已经做过、什么尚未验证。
