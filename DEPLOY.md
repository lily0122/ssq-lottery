# 将项目发布到 Streamlit Community Cloud

发布后你会得到一个 `https://……streamlit.app` 网址，可以发给别人，访客不需要安装Python。此项目已准备好部署文件，但尚未在你的账号下发布。

## 第一步：上传项目到 GitHub

1. 解压 `lottery-streamlit-cloud.zip`。
2. 登录 https://github.com ，右上角“+” → New repository。
3. Repository name 填 `ssq-lottery`，选择 Public，再点 Create repository。Public表示代码与附带的公开开奖数据也可被查看。
4. 点击 uploading an existing file（或者 Add file → Upload files）。
5. 将解压文件夹**里面的文件及文件夹**拖进去，保留 `data/` 和 `.streamlit/` 等目录结构，不要多套一层目录。不要直接上传ZIP。点击 Commit changes。
6. 检查仓库首页能直接看到 `app.py`、`lottery.py`、`cloud_data.py`、`fetch_official.py`、`requirements.txt`；`data/`内应有官方CSV、来源JSON、原始响应目录和导入模板。

上传包不包含虚拟环境、下载的依赖或任何账号密钥。`.streamlit/config.toml`为配置，不是密钥。

## 第二步：注册 Streamlit 并部署

1. 打开 https://share.streamlit.io/ ，选择使用 GitHub 登录，按页面提示完成注册及所需授权。
2. 点击 Create app，选择 Yup, I have an app。
3. Repository 选择你的 `用户名/ssq-lottery`。
4. Branch 选择 `main`；Main file path 填 `app.py`。
5. Advanced settings 中建议选择 Python 3.13（本项目已在3.13测试），无需填写Secrets。
6. 点击 Deploy，等待依赖安装及页面加载。网址中的名字可在App URL中自选，需尚未被使用。
7. 在应用的分享/设置中核实允许任何人查看；使用未登录的浏览器窗口打开网址，测试能否查看历史数据、生成25注、运行默认回测。将该网址分享给别人。

官方部署说明：https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy

## 网站上的数据更新

- 内置官方数据可直接使用，日期范围会显示在网页上。
- 访客在“官方历史数据”模式点击“检查官方更新”，服务端读取官方数据、校验并用于该访客当前会话。成功响应共享缓存1小时，降低官方请求频率。其他访客点击时可复用缓存；自己的上传数据和选号/回测结果不会共享。
- 更新失败或返回缺期/冲突时保留原数据，不使用模拟数据代替真实历史。
- 可下载更新后的官方CSV、来源JSON及原始响应ZIP。网页更新不会写入GitHub，也不是无人值守的定时更新。
- 若希望网站重启后也默认采用新数据：站点维护者在本机执行 `python fetch_official.py`，再把更新的 `data/official.csv`、`data/official.provenance.json` 和对应原始目录提交GitHub。也可将网页下载的ZIP中CSV和JSON上传到仓库的data目录，把ZIP中的raw目录放入data目录（保持来源JSON中的相对路径可解析）。GitHub更新后Streamlit会重新部署。
- 云服务器对中国福彩接口的访问可能受限制。如更新失败，使用CSV导入；当前附带2013年起的2086期记录不代表2003年至今完整历史。

## 多人使用和资源

上传CSV最多5MB、20000期；每次选号候选池上限10万；网页回测最多100期，候选池上限1万。回测结果在同一会话中保留，下载不会清空结果；更改相关参数后旧结果隐藏。公开版用于轻量使用，很多人同时运行长回测仍可能变慢。关闭浏览器/会话失效后私有会话数据不保证保留，应及时下载结果。

如果部署日志显示缺少CSV，检查是否上传了 `data/official.csv`；如果显示找不到模块，检查是否把文件放在仓库根目录；如果依赖安装失败，打开部署日志查看具体错误。当前无需额外Linux系统包，无数据库和付费API。
