# 植物浇水签到系统

一个简洁的植物浇水签到Web应用，支持多人签到、拍照记录、日历查看和数据导出。

## 版本

| 版本 | 目录 | 风格 | 说明 |
|------|------|------|------|
| A - 绿意盎然 | `plant-watering/` | 清新自然，绿色渐变，水滴动画 | 默认版本 |
| B - 手绘植物志 | `plant-watering-v4/` | 复古植物志，方格纸，印章按钮 | 文艺风格 |

## 快速开始

```bash
# 进入任一版本目录
cd plant-watering        # 版本A
# 或
cd plant-watering-v4     # 版本B

# 安装依赖
pip install -r requirements.txt

# 启动
python app.py
```

访问 http://localhost:5000

## 功能

- 多人签到（姓名选择/输入）
- 照片上传（支持多张）
- 签到记录列表
- 日历视图（标记浇水日期）
- 照片集（按日期分组浏览）
- 全屏照片查看器（左右滑动切换）
- 数据导出（Excel / CSV）
- 撤销签到
- 响应式设计（手机/电脑）

## 技术栈

- 后端：Python + Flask + SQLite
- 前端：HTML + CSS + JavaScript
- 部署：支持 Docker / Hugging Face Spaces
