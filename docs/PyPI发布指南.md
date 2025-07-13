# MX-RMQ PyPI发布指南

## 🎯 项目准备完成状态

✅ **已完成的准备工作：**
- [x] 创建了MIT许可证文件 (`LICENSE`)
- [x] 完善了项目配置 (`pyproject.toml`)
- [x] 安装了发布工具 (`build`, `twine`)
- [x] 创建了自动化发布脚本 (`scripts/publish.py`)
- [x] 成功构建了包文件 (`dist/mx_rmq-1.0.0.tar.gz`, `dist/mx_rmq-1.0.0-py3-none-any.whl`)
- [x] 包质量检查通过

## 📋 下一步操作清单

### 1. 注册PyPI账户
1. 访问 https://pypi.org/account/register/
2. 填写用户名、邮箱和密码
3. 验证邮箱地址
4. 启用双因素认证（推荐）

### 2. 注册TestPyPI账户（用于测试）
1. 访问 https://test.pypi.org/account/register/
2. 使用与PyPI相同的用户名和邮箱
3. 验证邮箱地址

### 3. 创建API Token
#### 对于TestPyPI：
1. 登录 https://test.pypi.org/
2. 进入 Account Settings → API tokens
3. 点击 "Add API token"
4. 名称：`mx-rmq-test`
5. 范围：选择 "Entire account" 或创建项目后选择特定项目
6. 复制生成的token（格式：`pypi-xxx...`）

#### 对于PyPI：
1. 登录 https://pypi.org/
2. 进入 Account Settings → API tokens
3. 点击 "Add API token"
4. 名称：`mx-rmq-prod`
5. 范围：选择 "Entire account" 或创建项目后选择特定项目
6. 复制生成的token（格式：`pypi-xxx...`）

### 4. 配置认证信息
创建 `~/.pypirc` 文件：

```ini
[distutils]
index-servers =
    pypi
    testpypi

[pypi]
repository = https://upload.pypi.org/legacy/
username = __token__
password = pypi-YOUR_PYPI_TOKEN_HERE

[testpypi]
repository = https://test.pypi.org/legacy/
username = __token__
password = pypi-YOUR_TESTPYPI_TOKEN_HERE
```

### 5. 更新项目URLs（重要）
修改 `pyproject.toml` 中的URLs，将 `your-username` 替换为您的实际GitHub用户名：

```toml
[project.urls]
Homepage = "https://github.com/your-username/mx-rmq"
Repository = "https://github.com/your-username/mx-rmq"
Documentation = "https://github.com/your-username/mx-rmq#readme"
Issues = "https://github.com/your-username/mx-rmq/issues"
```

### 6. 测试发布到TestPyPI
```bash
# 使用发布脚本
python scripts/publish.py

# 或手动执行
uv run twine upload --repository testpypi dist/*
```

### 7. 验证TestPyPI发布
```bash
# 在新的虚拟环境中测试安装
pip install -i https://test.pypi.org/simple/ mx-rmq

# 测试导入
python -c "from mx_rmq import RedisMessageQueue; print('导入成功!')"
```

### 8. 正式发布到PyPI
确认TestPyPI测试无误后：

```bash
# 使用发布脚本
python scripts/publish.py

# 或手动执行
uv run twine upload dist/*
```

### 9. 验证正式发布
```bash
# 测试正式安装
pip install mx-rmq

# 或使用uv
uv add mx-rmq
```

## 🚀 快速发布命令

完成上述准备工作后，您可以使用以下命令快速发布：

```bash
# 清理并重新构建
rm -rf dist/ build/ *.egg-info/
uv run python -m build

# 检查包
uv run twine check dist/*

# 发布到TestPyPI测试
uv run twine upload --repository testpypi dist/*

# 发布到正式PyPI
uv run twine upload dist/*
```

## 📝 注意事项

1. **版本号管理**：每次发布都需要更新 `pyproject.toml` 中的版本号
2. **GitHub仓库**：确保您的代码已推送到GitHub，URL配置正确
3. **依赖检查**：确保所有依赖都能正确安装
4. **测试覆盖**：建议在TestPyPI上充分测试后再发布到正式PyPI
5. **文档更新**：发布后更新README中的安装说明

## 🎉 发布成功后

发布成功后，用户就可以通过以下方式安装您的包：

```bash
# 使用pip
pip install mx-rmq

# 使用uv
uv add mx-rmq

# 指定版本
pip install mx-rmq==1.0.0
```

您的项目将在以下地址可见：
- PyPI: https://pypi.org/project/mx-rmq/
- TestPyPI: https://test.pypi.org/project/mx-rmq/ 