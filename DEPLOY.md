# question_repo · 部署到 autoyt2 同机 ECS

与 **autoyt2** 相同服务器（`/opt/autoyt2`、ECS `47.99.223.198`）：**阿里云 ECS + Docker Compose + RDS PostgreSQL**。  
本服务通过 autoyt2 的 **nginx 80 端口** 挂载子路径 **`/quiz/`**，无需额外开端口。

## 架构

```
浏览器 → ECS nginx:80 (autoyt2)
           ├─ /           autoyt2 前端
           ├─ /api/*      autoyt2 Django
           └─ /quiz/      question_repo (FastAPI:8765，Docker 内网)
                                    ↓
                              RDS PostgreSQL（库名 question_repo）
```

| 项目 | 值 |
|------|-----|
| ECS 公网 IP | `47.99.223.198`（与 autoyt2 相同） |
| autoyt2 目录 | `/opt/autoyt2` |
| 本仓库目录 | `/opt/question_repo` |
| 访问地址 | `http://47.99.223.198/quiz/` |

---

## 一、RDS 建库（一次性）

在 autoyt2 使用的 **同一 RDS** 上新建数据库（与 `answerbase` / autoyt2 库并列）：

```sql
CREATE DATABASE question_repo OWNER your_rds_user;
```

RDS 白名单、VPC 规则与 autoyt2 相同，无需在 ECS 安全组开放 5432。

---

## 二、首次部署（SSH 到 ECS）

```bash
ssh root@47.99.223.198

# 1. 克隆仓库（Deploy Key 或 HTTPS 任选）
mkdir -p /opt/question_repo && cd /opt/question_repo
git clone <你的 question_repo 仓库地址> .

# 2. 生产配置
cp .env.production.example .env.production
nano .env.production   # 填入 RDS 地址、账号、密码

# 3. 确认 autoyt2 网络存在（autoyt2 需先跑起来）
docker network ls | grep autoyt2
# 若无：cd /opt/autoyt2 && docker compose up -d

# 4. 构建并启动
cd /opt/question_repo
docker compose build
docker compose up -d

# 5. 接入 autoyt2 nginx（见 deploy/nginx-autoyt2.snippet）
nano /opt/autoyt2/nginx.conf
# 在 location / { 之前粘贴 snippet 内容
cd /opt/autoyt2
docker compose build nginx && docker compose up -d nginx
```

浏览器访问：**http://47.99.223.198/quiz/**

---

## 三、修改 autoyt2 nginx（必做）

编辑 `/opt/autoyt2/nginx.conf`，在 `location / {` **之前**加入：

```nginx
location /quiz/ {
    proxy_pass http://question_repo_quiz:8765/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Prefix /quiz;
    proxy_read_timeout 120;
}
```

重建 nginx：

```bash
cd /opt/autoyt2 && docker compose build nginx && docker compose up -d nginx
```

> `question_repo_quiz` 是 compose 里固定的 `container_name`，nginx 通过 Docker 网络 `autoyt2_default` 访问。

若网络名不是 `autoyt2_default`，在 ECS 上执行 `docker network ls` 查看后，修改本仓库 `docker-compose.yml` 里 `networks.autoyt2.name`。

---

## 四、日常更新

```bash
cd /opt/question_repo
git pull
docker compose build && docker compose up -d
```

仅改环境变量、不改代码：

```bash
nano .env.production
docker compose up -d --force-recreate quiz
```

跳过启动时重复导入（加快重启）：

```bash
# .env.production 增加
SKIP_IMPORT=1
```

---

## 五、本机验证（部署前）

```bash
cp .env.production.example .env.production
# 编辑 PGHOST 等

docker compose build
docker compose up
curl -s http://127.0.0.1:8765/api/subjects   # 需临时映射端口测试时可改 compose
```

---

## 六、与 autoyt2 的差异

| 项目 | autoyt2 | question_repo |
|------|---------|---------------|
| 框架 | Django + Vue | FastAPI + 静态页 |
| 对外路径 | `/` `/api/` | `/quiz/` |
| 数据库 | autoyt2 库 | **question_repo** 独立库 |
| 镜像 | web + nginx | 仅 quiz 容器 |
| CI | GitHub Actions | 暂用手动 `git pull` + compose |

后续可加 GitHub Actions：SSH 到 ECS 执行 `git pull && docker compose up -d --build`，Secrets 参考 autoyt2 的 `ECS_HOST` / Deploy Key。

---

## 七、常见问题

| 现象 | 处理 |
|------|------|
| `/quiz/` 502 | `docker ps` 看 `question_repo_quiz` 是否 Up；是否已改 nginx 并 rebuild |
| 数据库连接失败 | 检查 `.env.production` 的 RDS 外网地址与白名单 |
| 页面无样式 | 强制刷新；确认访问 URL 带尾斜杠 `/quiz/` |
| 题库为空 | 查看容器日志：`docker compose logs quiz`；手动 `docker compose exec quiz python3 scripts/import_pay_questions.py` |
| 切换/重建题库 | 将爱真题付费文件放入 `questions/pay/`，执行 `python3 scripts/import_pay_questions.py`（会先跑 `001_clear_all_questions.sql` 清空旧题） |
