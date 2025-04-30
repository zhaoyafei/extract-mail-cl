import os

# 创建templates目录(如果不存在)
if not os.path.exists('templates'):
    os.makedirs('templates')
    print("Created templates directory")
else:
    print("Templates directory already exists")
