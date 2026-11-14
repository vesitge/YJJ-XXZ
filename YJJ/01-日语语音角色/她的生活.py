# -*- coding: utf-8 -*-
"""
她的生活 —— 最小状态机骨架

设计原则：
  1. 时间用真实时钟。程序不开，她的日子照过。
  2. 骨架由作者写死（作息表），不由模型随机决定。
  3. 状态是真值（存档），模型只在需要时把状态翻译成人话。
  4. 一个时间片一个决定，一天只有 9 片，跑一天是瞬间的事。

不依赖第三方库。python 她的生活.py 就能跑。
"""

import argparse
import json
import os
import random
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
SAVE = os.path.join(HERE, "她的生活.json")

# ---------------------------------------------------------------- 骨架
# 格式：(开始, 结束, 地点, 在做什么, 每小时体力变化)
# 最后一段可以跨天（结束时间 < 开始时间）

WORKDAY = [
    ("07:30", "08:10", "家",   "刚起床",     -0.12),
    ("08:10", "09:00", "路上", "通勤",       -0.08),
    ("09:00", "12:00", "公司", "上班",       -0.05),
    ("12:00", "13:00", "公司", "吃午饭",     +0.05),
    ("13:00", "18:00", "公司", "上班",       -0.05),
    ("18:00", "18:40", "路上", "通勤",       -0.09),
    ("18:40", "20:00", "家",   "做饭",       -0.04),
    ("20:00", "23:30", "家",   "自由时间",   +0.05),
    ("23:30", "07:30", "家",   "睡了",       +0.12),
]

WEEKEND = [
    ("09:00", "10:00", "家",   "睡到自然醒", +0.06),
    ("10:00", "12:00", "家",   "收拾屋子",   -0.05),
    ("12:00", "13:00", "家",   "吃饭",       +0.05),
    ("13:00", "17:30", "外面", "出门",       -0.05),
    ("17:30", "19:00", "家",   "做饭",       -0.04),
    ("19:00", "00:30", "家",   "自由时间",   +0.03),
    ("00:30", "09:00", "家",   "睡了",       +0.10),
]

# 随机事件：(触发条件的地点, 文本, 心情变化, 体力变化, 权重)
# 条件为 None 表示任何地方都可能
EVENTS = [
    (None,   "便利店的灯还亮着，进去转了一圈",     +0.04,  0.00, 3),
    ("路上", "路上堵了好一会儿",                  -0.08, -0.03, 6),
    ("公司", "被叫去开了个没头没尾的会",          -0.14, -0.04, 4),
    ("公司", "同事递了杯热咖啡过来",              +0.07,  0.00, 4),
    ("公司", "忙到忘了吃中饭",                    -0.12, -0.06, 3),
    ("公司", "主管从背后路过，看了眼屏幕",        -0.06,  0.00, 3),
    ("家",   "把堆了两天的衣服洗了",              +0.06, -0.02, 4),
    ("家",   "翻到手机里一张旧照片，看了很久",    +0.03,  0.00, 3),
    ("外面", "路过花店，犹豫了一下还是走了",      -0.05,  0.00, 4),
    ("外面", "买了杯热的，站在路边喝完了",        +0.08,  0.00, 4),
    (None,   "下起了那种不大不小的雨",            -0.05, -0.02, 4),
    (None,   "手机震了一下，是群里在聊没营养的",  +0.02,  0.00, 3),
]

MAX_EVENTS_PER_DAY = 2   # 一天最多发生 2 件事。多了就成了连续剧，不像日子


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def hm(s):
    h, m = s.split(":")
    return int(h), int(m)


# ---------------------------------------------------------------- 状态
@dataclass
class Her:
    name: str = "凉"
    last_tick: str = ""          # ISO 时间，上次推进到哪
    place: str = "家"
    activity: str = "自由时间"
    energy: float = 0.7          # 0~1 体力
    mood: float = 0.1            # -1~1 心情
    closet: str = "居家"          # 当前穿着（给图片层用）
    closeness: float = 0.3       # 0~1 和你之间
    unresolved: list = field(default_factory=list)   # 她心里没放下的事
    recent_actions: list = field(default_factory=list)  # 最近做过的动作（防重复）

    def to_dict(self):
        return asdict(self)


# ---------------------------------------------------------------- 世界
class Life:
    def __init__(self, path=SAVE):
        self.path = path
        self.state = Her()
        self._counter = {}      # 每天发生了几件事，跨调用保留
        self.load()

    # ---- 存档
    def load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    d = json.load(f)
                for k, v in d.items():
                    if hasattr(self.state, k):
                        setattr(self.state, k, v)
            except Exception as e:
                print(f"[存档读不出来，用新的一天开始] {e}")

    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.state.to_dict(), f, ensure_ascii=False, indent=2)

    # ---- 作息表
    @staticmethod
    def _table(day):
        return WORKDAY if day.weekday() < 5 else WEEKEND

    def _switch_points(self, day):
        out = []
        for row in self._table(day):
            h, m = hm(row[0])
            out.append(day.replace(hour=h, minute=m, second=0, microsecond=0))
        return sorted(out)

    def _next_switch(self, t):
        day = t.replace(hour=0, minute=0, second=0, microsecond=0)
        later = [x for x in self._switch_points(day) if x > t]
        if later:
            return later[0]
        return self._switch_points(day + timedelta(days=1))[0]

    def _activity_at(self, t):
        """t 这一刻，她处在哪一段里。返回 (这段的开始时间, 行)"""
        day = t.replace(hour=0, minute=0, second=0, microsecond=0)
        best = None
        for row in self._table(day):
            h, m = hm(row[0])
            st = day.replace(hour=h, minute=m, second=0, microsecond=0)
            if st <= t:
                best = (st, row)
        if best:
            return best
        # 今天还没到第一个锚点：说明还在昨晚最后一段（通常是「睡了」）
        prev = day - timedelta(days=1)
        row = self._table(prev)[-1]
        h, m = hm(row[0])
        st = prev.replace(hour=h, minute=m, second=0, microsecond=0)
        return st, row

    # ---- 推进
    def advance_to(self, now):
        """把她的时间从 last_tick 推到 now，返回这段时间里发生的事。"""
        if not self.state.last_tick:
            self.state.last_tick = (now - timedelta(hours=1)).isoformat()
        t = datetime.fromisoformat(self.state.last_tick)
        events = []
        day_counter = self._counter
        guard = 0
        while t < now and guard < 2000:
            guard += 1
            nxt = min(self._next_switch(t), now)
            self._step(t, nxt, events, day_counter)
            t = nxt
        self.state.last_tick = now.isoformat()
        # 把状态对齐到「此刻」，别停在上一片里
        _, row = self._activity_at(now)
        self.state.place, self.state.activity = row[2], row[3]
        return events

    def _step(self, t0, t1, events, day_counter):
        _, row = self._activity_at(t0)
        _, _, place, act, rate = row

        hours = (t1 - t0).total_seconds() / 3600.0

        # 位置和活动
        self.state.place = place
        self.state.activity = act

        # 体力
        self.state.energy = clamp(self.state.energy + rate * hours, 0.0, 1.0)

        # 情绪缓慢回中
        self.state.mood *= (1 - 0.02 * hours)
        self.state.mood = clamp(self.state.mood, -1, 1)

        # 太累会拉低心情
        if self.state.energy < 0.25:
            self.state.mood -= 0.01 * hours
            self.state.mood = clamp(self.state.mood, -1, 1)

        # 穿着按活动换（给图片层用）
        if act in ("睡了", "刚起床", "睡到自然醒"):
            self.state.closet = "睡衣"
        elif act in ("上班", "通勤", "吃午饭"):
            self.state.closet = "通勤装"
        elif act in ("自由时间", "收拾屋子", "做饭", "吃饭"):
            self.state.closet = "居家"
        else:
            self.state.closet = "外套"

        # 随机事件：一天限量，同一件事不重复
        day_key = t1.date().isoformat()
        if act != "睡了" and random.random() < 0.22:
            if day_counter.get(day_key, 0) < MAX_EVENTS_PER_DAY:
                pool = [e for e in EVENTS
                        if (e[0] is None or e[0] == place)
                        and e[1] not in self.state.recent_actions]
                if pool:
                    _, text, dm, de, _w = random.choice(pool)
                    day_counter[day_key] = day_counter.get(day_key, 0) + 1
                    self.state.mood = clamp(self.state.mood + dm, -1, 1)
                    self.state.energy = clamp(self.state.energy + de, 0, 1)
                    events.append({"at": t1.isoformat(), "text": text,
                                   "mood": dm})
                    self._remember(text)

    def _remember(self, text):
        self.state.recent_actions.append(text)
        self.state.recent_actions = self.state.recent_actions[-8:]

    # ---- 给前端看
    def viewing(self, now=None):
        now = now or datetime.now()
        h = now.hour + now.minute / 60
        if 5 <= h < 9:
            tod = "清晨"
        elif 9 <= h < 17:
            tod = "白天"
        elif 17 <= h < 19.5:
            tod = "傍晚"
        elif 19.5 <= h < 23:
            tod = "夜晚"
        else:
            tod = "深夜"

        m = self.state.mood
        if m > 0.35:
            face = "开心"
        elif m > 0.05:
            face = "平静"
        elif m > -0.25:
            face = "有点闷"
        else:
            face = "低落"

        home = self.state.place == "家"
        asleep = self.state.activity == "睡了"

        if asleep:
            scene = "家·卧室·夜"
            who = "睡着了"
        elif home:
            scene = f"家·{tod}"
            who = "在"
        else:
            scene = f"{self.state.place}·{tod}"
            who = "不在家"

        return {
            "scene": scene,
            "who": who,
            "place": self.state.place,
            "activity": self.state.activity,
            "face": face,
            "closet": self.state.closet,
            "energy": round(self.state.energy, 2),
            "mood": round(self.state.mood, 2),
        }


# ---------------------------------------------------------------- 模型钩子
def narrate(events, state):
    """
    把「发生的事」翻成人话。
    这里先用模板，不花一分钱。
    以后换成真模型，只改这个函数，其它都不用动。
    """
    if not events:
        return "这几个小时没什么特别的，就是过着。"
    head = "；".join(e["text"] for e in events)
    if state.mood < -0.2:
        return f"{head}。回来的时候脸色不太好。"
    if state.mood > 0.4:
        return f"{head}。她看起来心情不错。"
    return f"{head}。"


# ---------------------------------------------------------------- 命令行
def show(life, now):
    v = life.viewing(now)
    print()
    print(f"  ── {now:%m-%d %H:%M} ──")
    print(f"  场景    {v['scene']}")
    print(f"  她在    {v['who']}（{v['activity']}）")
    print(f"  神情    {v['face']}   穿着 {v['closet']}")
    print(f"  体力    {v['energy']:.2f}   心情 {v['mood']:+.2f}")
    print()


def demo(hours):
    """从今天 0 点开始，按小时推进，把一整天打出来。不写存档。"""
    life = Life.__new__(Life)
    life.path = SAVE
    life.state = Her()
    life._counter = {}
    random.seed(20261109)
    start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    life.state.last_tick = start.isoformat()
    print(f"\n  ══ 模拟 {start:%m-%d} 这一天 ══\n")
    t = start
    end = start + timedelta(hours=hours)
    while t < end:
        nxt = min(t + timedelta(minutes=30), end)
        evs = life.advance_to(nxt)
        v = life.viewing(nxt)
        line = (f"  {nxt:%H:%M}  {v['scene']:<12} {v['activity']:<8} "
                f"体力{v['energy']:.2f}  心情{v['mood']:+.2f}  {v['face']}")
        print(line)
        for e in evs:
            print(f"          └ {e['text']}")
        t = nxt
    print()


def main():
    p = argparse.ArgumentParser(description="她的生活 · 最小状态机")
    p.add_argument("--demo", type=float, default=0,
                   help="不出存档，模拟一天看效果（单位：小时）")
    p.add_argument("--fast", type=float, default=0,
                   help="快进多少小时（会写存档）")
    p.add_argument("--reset", action="store_true", help="删掉存档，重新开始")
    a = p.parse_args()

    if a.reset and os.path.exists(SAVE):
        os.remove(SAVE)
        print("  存档已删除。")

    if a.demo:
        demo(a.demo)
        return

    life = Life()
    now = datetime.now()

    if a.fast:
        now = datetime.fromisoformat(life.state.last_tick or now.isoformat()) \
              + timedelta(hours=a.fast)

    evs = life.advance_to(now)
    life.save()

    show(life, now)
    if evs:
        print("  这期间发生了什么：")
        for e in evs:
            print(f"    · {e['text']}")
        print(f"\n  说给你听：{narrate(evs, life.state)}\n")
    else:
        print("  这几个小时没什么特别的。\n")


if __name__ == "__main__":
    main()
