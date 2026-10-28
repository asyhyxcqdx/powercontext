# Ubuntu 22.04 服务器部署指南（MiniMax SDD）

## 服务器与网络

服务器 Ubuntu 22.04 的 `/root/projects/powercontext/minimax/` 用于代码和真实运行记录。PowerContext 仅监听 `127.0.0.1:8000`，业务 seekdb 由 Python 嵌入运行，**无需开放 8000、2881 等公网端口**。MiniMax 是向外发起的 HTTPS 请求。

## A. Windows PowerShell 上传 ZIP

在浏览器下载 **MiniMax_SDD_Server_ReadyKit_20261028.zip** 到 Windows 下载目录。下面使用你此前连接的服务器 `1.94.177.105`。如果 IP 已改变，只修改 `$server`；不要把服务器密码写在脚本或聊天记录中。

```powershell
$zip = Join-Path $env:USERPROFILE 'Downloads\MiniMax_SDD_Server_ReadyKit_20261028.zip'
if (!(Test-Path $zip)) { throw "找不到下载的 ZIP: $zip" }
$server = '1.94.177.105'
scp $zip "root@${server}:/root/minimax_server.zip"
ssh "root@$server"
```

## B. 服务器初始化 Git 仓库（只需要一次）

```bash
apt-get update
apt-get install -y git curl ca-certificates unzip
mkdir -p /root/projects
cd /root/projects
# 如果已存在，请跳过 clone。
# 自己私有赛题仓库应已导入同名的 2026-competition-ecosystem 分支。
git clone --branch 2026-competition-ecosystem https://github.com/asyhyxcqdx/powercontext.git powercontext
cd /root/projects/powercontext
git branch --show-current
git status --short
```

HTTPS 私有仓库需要 GitHub token 或 SSH Key；不能使用 GitHub 登录密码做 HTTPS Git 身份验证。不要为了绕过认证把 token 写入仓库远程 URL。已有仓库只需先 `git fetch origin 2026-competition-ecosystem` 并切到对应分支。

## C. 解压到指定分支的 minimax 目录

```bash
cd /root/projects/powercontext
unzip -Z1 /root/minimax_server.zip | head
if [ -e minimax ]; then
  echo 'minimax/ 已存在，先备份并人工合并，避免覆盖已有作品'
else
  unzip -oq /root/minimax_server.zip 'minimax/*' -d /root/projects/powercontext
fi
bash minimax/scripts/verify_server_branch.sh
cd minimax
```

## D. 安装隔离环境、填写 MiniMax Key

```bash
bash scripts/install_server.sh
cp -n .env.example .env
chmod 600 .env
nano .env
# 编辑：MINIMAX_API_KEY=自己的有效 Key
# 其余默认先保持不变，使用嵌入式 seekdb
```

`install_server.sh` 使用 uv 安装 Python 3.12，创建 `minimax/.venv`，安装 `pylibseekdb==1.4.0.post1`、PyMySQL、pytest，并将 PowerContext `1.4.1` 安装到项目独立的 `.powercontext-venv/`，不会替换其它赛题的 PowerContext 版本。请至少保证服务器有足够的磁盘和内存，嵌入式 seekdb 初始化会消耗资源。

## E. 运行真实验收（务必保留全部日志）

```bash
cd /root/projects/powercontext/minimax
bash scripts/verify_server_branch.sh
bash scripts/full_demo_server.sh
bash scripts/check_ready_to_commit.sh
cat evidence/15_submission_audit.json
```

此过程真实调用 seekdb SQL、MiniMax API、PowerContext HTTP；从初始代码开始，修改前目标断言失败，修改后相同测试通过，最后将 PowerContext Server 停止再启动并读取已保存的状态。没有有效 Key 或外网连接，无法生成在线证据，不得声称通过。

如果报错：

```bash
cd /root/projects/powercontext/minimax
tail -n 100 runtime/powercontext-server.log
find evidence/runs -type f -name '*.json' | tail -n 20
.venv/bin/python -m sddflow.cli doctor
```

## F. 提交同名分支的 commit SHA

```bash
cd /root/projects/powercontext
git status --short
git add minimax
git diff --cached --check
git diff --cached --stat
git commit -m 'feat(minimax): SDD context with MiniMax seekdb PowerContext'
git rev-parse HEAD
git push origin 2026-competition-ecosystem
```

只在完成在线验收后才提交对应的真实记录。切勿提交 `.env`、`runtime`、Key、密码。审核 `.gitignore` 和 `git status --short`，确认只改变 `minimax/`。
