# 测试与验证

## 后端

基础检查：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
```

全量单元测试：

```bash
PYTHONPATH=backend/src python3 -m unittest discover -s tests -v
```

## 前端

```bash
cd web
npm test
npm run build
```

## 文档变更检查

文档结构调整后至少执行：

```bash
find docs -maxdepth 3 -type f -name '*.md' | sort
rg -n "docs/product/|OA 集成当前 app 技术方案" README.md docs backend web deploy -g '*.md'
```

如果只是文档重排，不要求运行业务测试；但必须检查路径和索引不会继续指向已移动位置。
