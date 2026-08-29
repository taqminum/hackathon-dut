# Serendipity Navigation（偶遇导航）

Hackathon 项目：先做网页版，再尝试打包为 Android App 壳。

详见 `docs/superpowers/plans/2026-08-25-serendipity-navigation.md`。

## 快速开始

- 后端：见 `backend/README.md`
- 网页端：见 `webapp/README.md`

## 一键预览

```bash
cd backend
uvicorn app.main:app --reload --env-file .env
```

打开 `http://localhost:8000` 即可预览网页版。

说明：
- 已内置大连演示数据，无需高德 Key 也可体验。
- 首页提供 3 个快速体验按钮，可一键查看 demo。

## 文档索引

- 计划与边界：`docs/superpowers/plans/2026-08-25-serendipity-navigation.md`
- 团队分工：`docs/superpowers/specs/team.md`
- 当前进展与待确认项：`docs/superpowers/status/2026-08-25.md`
