# 部署与开发说明

[返回项目首页](../README.md)

本仓库为脱敏源码，账号、应用、计划、素材和场次标识均为虚构占位值，不包含生产凭证与业务数据。测试数据不代表真实运营结果。

浏览器辅助脚本需要另外提供宿主；平台接入、模型调用和交付需要自行配置。云端模型会接收输入素材，使用前应确认素材适合提交给对应服务。

## 本地准备

使用 Python 3.12；JavaScript 测试需要支持 `require()` 加载本项目 `.mjs` 的 Node.js 版本（本次验证版本见脱敏说明）。

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests
node --test tests/*.cjs
```

模型权重未打包。根据使用的 ASR 模型另行下载；没有真实素材、密钥和模型时，不能据此声称端到端可用。

## 配置

`.env.example` 仅说明环境变量名称，程序不会自动加载此文件。密钥应通过环境变量或本机钥匙串提供，禁止提交。

`config/clip_daily_accounts.json` 是虚构账号示例。源码中其他账号、计划、应用标识也已替换为以 `9000` 开头的虚构数值，用于保留校验及测试结构，并非可用账户。真实部署前需要统一配置相关常量与适配器，不能仅修改这一份 JSON。

上传授权模块默认指向本副本的 `config/local_qianchuan_service.py`（未提供）；也可通过 `LIVECLIP_QIANCHUAN_SERVICE` 显式指定。日报模块需另行配置其 `SERVICE` 路径。OAuth 示例使用独立的钥匙串条目名称；不要将生产凭证复制进本仓库。

## 处理自有素材

```sh
.venv/bin/python -m liveclip data/example/source_6min.mp4 --output outputs/review_001 --provider deepseek --asr-model small
```

输出目录应为新目录。模型、转写和抽帧审核可能失败或无法找到合格片段，缺失结果不等于零；抽样检查不等于检查每一帧。上传、授权服务及消息交付入口会产生外部操作，只有显式配置并确认目标后才使用。

## 发布范围

仅提交本目录内源码、测试、通用文档和示例配置。`.gitignore` 排除本地配置、数据库、媒体、凭证、模型和运行输出。本仓库没有附带生产 Git 历史，也未包含开源许可证；如需公开授权他人复用，请由代码权利人选择许可证。


[脱敏与验证说明](SANITIZATION.md)
