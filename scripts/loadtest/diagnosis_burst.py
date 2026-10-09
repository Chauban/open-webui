"""第一次通读的并发试打：N 个学生同时交初稿时，模型商扛不扛得住。

一节课 60 人几乎同时点「确认这是我的初稿」，每人触发一次逐项诊断（20～50 秒、开思考）。
这一跳打的是真实模型（经本机后端的 /api/chat/completions 转发），所以测的是
「模型商的并发/限流 + 后端转发」，不是服务器容量——容量见 README 的 k6 压测。

用法（仓库根目录，本机后端在 8080 跑着）：
    $env:WEBUI_SECRET_KEY = (Get-Content backend\\.webui_secret_key -Raw).Trim()
    backend\\.venv\\Scripts\\python.exe scripts\\loadtest\\diagnosis_burst.py --n 60 --model deepseek-flash
需要管理员账号（脚本里读环境变量 RW_ADMIN_EMAIL / RW_ADMIN_PASSWORD）。
会真实消耗模型额度：60 次约几十万 token。
"""

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import httpx

sys.stdout.reconfigure(encoding="utf-8")
BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

from open_webui.services.education.revision_items import (  # noqa: E402
    build_diagnosis_messages,
    parse_diagnosis,
)

DRAFT = """《杜甫晚年夔州诗研究》文献综述

杜甫是唐代最伟大的诗人之一，被誉为"诗圣"。安史之乱以后，杜甫漂泊西南，于大历元年（766年）移居夔州，在此居住近两年，创作诗歌四百余首。本文拟对夔州诗的研究现状进行梳理。

一、关于夔州诗的思想内容研究
有学者指出，杜甫夔州诗集中体现了诗人晚年对国家命运的忧虑和对个人身世的感慨。《秋兴八首》以"故国平居有所思"为核心，将长安的盛衰与个人的漂泊结合起来，体现出深沉的家国情怀。

二、关于夔州诗的艺术特色研究
莫砺锋在《杜甫诗歌讲演录》中认为，杜甫夔州时期的七律创作数量多、质量高，形成了"沉郁顿挫"的典型风格。也有研究者认为，夔州诗在语言上趋于老成。

三、关于夔州诗的地域文化研究
近年来，部分学者开始从地域文化角度研究夔州诗。夔州地处三峡，杜甫在诗中大量描写了当地的风俗民情。

四、研究不足与展望
目前研究仍存在一些不足。第一，个案研究较少；第二，比较研究不够深入；第三，跨学科研究有待加强。

参考文献
[1] 莫砺锋. 杜甫诗歌讲演录[M]. 桂林: 广西师范大学出版社, 2007.
[2] 萧涤非. 杜甫研究[M]. 济南: 齐鲁书社, 1980."""

LABELS = [
    "综述只写已有的研究", "选题基于已有研究的不足", "出处与参考文献", "文献的相关性与充分性",
    "按一定原则分类", "每篇文献的介绍", "学术表达", "标题与引言",
]
CRITERIA = [SimpleNamespace(key=f"criterion_{i + 1}", label=label) for i, label in enumerate(LABELS)]


async def one(client, url, headers, model, messages, index):
    started = time.monotonic()
    try:
        res = await client.post(
            url,
            headers=headers,
            json={"model": model, "messages": messages, "stream": False},
            timeout=300,
        )
        elapsed = time.monotonic() - started
        if res.status_code != 200:
            return {"i": index, "ok": False, "status": res.status_code, "secs": elapsed, "err": res.text[:160]}
        content = res.json()["choices"][0]["message"]["content"]
        try:
            parse_diagnosis(content, DRAFT, CRITERIA)
            parsed = True
        except Exception:
            parsed = False
        return {"i": index, "ok": True, "status": 200, "secs": elapsed, "parsed": parsed}
    except Exception as error:  # 超时、连接被拒
        return {"i": index, "ok": False, "status": type(error).__name__, "secs": time.monotonic() - started}


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=60)
    parser.add_argument("--model", default="deepseek-flash")
    parser.add_argument("--base", default="http://localhost:8080")
    args = parser.parse_args()

    async with httpx.AsyncClient() as client:
        signin = await client.post(
            f"{args.base}/api/v1/auths/signin",
            json={"email": os.environ["RW_ADMIN_EMAIL"], "password": os.environ["RW_ADMIN_PASSWORD"]},
        )
        token = signin.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        config = (await client.get(f"{args.base}/api/v1/configs/education", headers=headers)).json()
        task_prompt = config["EDUCATION_TASK_PROMPTS"]["revise_draft"]
        messages = build_diagnosis_messages(task_prompt, CRITERIA, DRAFT)

        started = time.monotonic()
        results = await asyncio.gather(
            *[one(client, f"{args.base}/api/chat/completions", headers, args.model, messages, i) for i in range(args.n)]
        )
        wall = time.monotonic() - started

    ok = [r for r in results if r["ok"]]
    failed = [r for r in results if not r["ok"]]
    secs = sorted(r["secs"] for r in ok)
    print(f"并发 {args.n}，模型 {args.model}，总墙钟 {wall:.0f}s")
    print(f"成功 {len(ok)}，失败 {len(failed)}，能解析成结论表 {len([r for r in ok if r.get('parsed')])}")
    if secs:
        print(
            f"耗时 中位 {statistics.median(secs):.0f}s，P90 {secs[int(len(secs) * 0.9) - 1]:.0f}s，最长 {secs[-1]:.0f}s"
        )
    for r in failed[:10]:
        print("失败:", json.dumps(r, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
