# 拾作 · 我的项目收藏

把自己做过的网站、在线工具、GitHub 仓库和学习作品，整理成可以分类查看的小卡片。

## 使用

- 打开网页，或下载仓库中的 `index.html` 后用 Chrome、Edge、Firefox 打开，无需安装 Python。
- 粘贴项目网址，选择分类，点击 **生成卡片**。
- 点击每张卡片底部的 **编辑**，修改标题、介绍、网址、分类、状态、标签和封面；点 **保存卡片** 后生效。
- 点击左侧分类查看同类作品；卡片底部的分类菜单可以直接移动卡片。
- 分类旁的省略号支持改名、换颜色和删除分类。删除分类会保留作品，并移入“未分类”。
- 点击封面或标题，打开对应项目网址。

静态网页用网址域名生成初始卡片，可以自行改标题并上传项目截图。它不会自动拍摄网站截图。GitHub 公开仓库可通过“GitHub 导入”预览并选择收录；无法读取时仍可直接粘贴仓库网址。

## 数据保存

网页里的卡片、笔记和上传的封面保存在当前浏览器的 IndexedDB，不会写回这个 GitHub 仓库。每个人打开网页时使用自己的作品库。

固定使用同一浏览器和网页地址，并定期点击 **导出备份**。换电脑、换浏览器、从本地文件切换到在线网页或清理浏览器数据前，先导出 JSON，再到新位置导入。隐私窗口不适合长期保存作品。

公开网页初始为空。部署新版不会覆盖浏览器里已有的卡片。JSON 备份兼容旧版 v1 和新版 v2；包含卡片、分类、封面与时间，导入会补充新记录，跳过已有网址和相同记录。

## 可选：Python 本地服务

如需自动读取公开网页提供的标题、介绍和 Open Graph 封面，可使用 Python 3.12+ 服务版，没有第三方运行依赖：

```bash
python3 app.py --open
```

Windows 可双击 `start.bat`，或运行 `py -3.12 app.py --open`；macOS / Linux 可运行 `./start.command`。命令窗口需保持运行，用完按 Ctrl+C 停止；端口占用时添加 `--port 8766`。

服务版将数据存入 `data/projects.sqlite3`，支持旧数据自动迁移。它与浏览器版的存储独立，可通过 JSON 备份相互迁移。服务仅监听本机地址，没有账号系统，不适合直接开放到公网。

读取网站信息失败时仍会保存网址卡片；本机和内网网址可保存为链接，不自动抓取内容。外部封面图片依赖网络，上传的封面可离线查看。

## 开发与构建

```bash
python3 -m unittest discover -s tests -v
python3 build_standalone.py --public
```

`--public` 生成仓库根目录的 `index.html`，不会读取本地数据库或包含个人卡片。修改 `static` 下的界面后，重新构建再提交 `index.html`。

如需包含当前 SQLite 记录的个人离线副本，运行 `python3 build_standalone.py`，输出 `打开项目库.html`。该文件、个人截图、数据库、备份和 `.env` 已加入 Git 忽略规则，不能作为公开发布文件。

## GitHub Pages

仓库包含 `.github/workflows/pages.yml`。在 GitHub 仓库的 **Settings → Pages → Source** 选择 **GitHub Actions**。推送 `main` 或手动运行工作流后，会先执行测试，再构建不含个人数据的网页并部署。

`index.html` 也可以直接部署到任何支持静态 HTML 的服务。

## 界面参考

参考 [Linkwarden](https://github.com/linkwarden/linkwarden) 的分类整理方式和 [Karakeep](https://github.com/karakeep-app/karakeep) 的封面卡片浏览方式；本项目面向个人整理，保持轻量、无需账号。
