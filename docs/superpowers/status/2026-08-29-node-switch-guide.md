# Node 22 切换与 Claude 安装操作手册

> 给人执行的步骤，不是给 AI 的。全部在 PowerShell 里跑。
> 基线提交 `44c8cd7` 已包含全部改动，出任何问题都能退回。

---

## 结论先说

- **认证不会丢，不需要重新登录。** 原因见最后一节。
- 需要做的只有两件事：切版本、装 claude。
- 切回去也是一条命令，随时可逆。

---

## 步骤

### 1. 切到 Node 22

```powershell
nvm use 22.23.2
node -v
```

第二条必须显示 `v22.23.2` 再往下做。**这一步之后当前的 Claude 会话就没了**
（claude 只装在 20 下），所以先把要交接的话说完再切。

如果 `nvm use` 报权限错误，用管理员身份重开 PowerShell 再执行 —— nvm 切版本
要改 `C:\Program Files\nodejs` 这个符号链接。

### 2. 装 Claude Code

```powershell
npm i -g @anthropic-ai/claude-code
claude --version
```

顺序不能反：必须先切到 22，再装，否则装到 20 里去了。

### 3. 启动，直接干活

```powershell
cd D:\claude\黑客松\hackathon-dut
claude
```

**不需要 `/login`**，认证是共用的（见下一节）。

启动后把 `docs/superpowers/status/2026-08-29-handover-3.md` 第一部分那段提示词
发给它，它会自己读文档并开始工作。

### 4. 确认前端环境真的通了

这是切版本的唯一目的，值得当场验一下：

```powershell
cd D:\claude\黑客松\hackathon-dut\webapp
npm run test:run
```

期望看到 `3 failed | 74 passed` —— 这三条失败是**已知的、待修的**
（见 handover-3 第二部分第 1 条），不是环境问题。能看到这个数字就说明
vitest 起来了，前三轮在 Node 20 下连这一步都到不了。

---

## 关于认证：为什么不用重新登录

两样东西存在不同的地方，互不影响：

| 东西 | 存放位置 | 跟 node 版本有关吗 |
|---|---|---|
| claude 这个程序 | `...\nvm\v22.23.2\node_modules\` | 有，每个版本一份 |
| 登录凭证、配置、项目记忆 | `C:\Users\lenovo\.claude\` | **无关** |

`nvm use` 只切换「用哪个 node 跑程序」，不会动 `C:\Users\lenovo\.claude\`。
所以在 22 下装好的 claude 启动后读的还是同一份配置，登录状态、`.claude` 下的
项目记忆目录都在原位。

**你只需要装程序，不需要重新认证。**

---

## 如果要切回 Node 20

```powershell
nvm use 20.12.0
node -v
```

20 下的 claude 一直都在，没被动过。两个版本各有一份 claude，互不干扰。

---

## 出问题怎么办

**`npm run build` 或 `npm i` 报错**：先确认 `node -v` 是 22。如果是 22 还报错，
`node_modules` 可能是 Node 20 下装的，删掉重装：

```powershell
cd D:\claude\黑客松\hackathon-dut\webapp
Remove-Item node_modules -Recurse -Force
npm install
```

**dist 被构建覆盖坏了**：

```powershell
cd D:\claude\黑客松\hackathon-dut
git checkout 44c8cd7 -- webapp/dist
```

**想整个退回今天的状态**：

```powershell
git reset --hard 44c8cd7
```

会丢弃所有未提交改动，执行前先 `git status` 看一眼。

**后端跑不起来**：不要用系统 python，用虚拟环境里那个：

```powershell
cd D:\claude\黑客松\hackathon-dut\backend
.venv\Scripts\python.exe -m pytest -q
```

期望 193 passed。后端和 Node 版本完全无关，切版本不会影响它。
