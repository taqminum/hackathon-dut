"""用户偏好：把「还不错 / 一般」的反馈变成下一次推荐的打分依据。

这个模块过去是死类（无 import、无测试），只存了 mode 和一串 tags。
现在它承担 P2-2 的闭环：`/api/feedback` 写入 -> `scorer.score` 读出。

为什么要有它：赛题是「制造一点意外」，而「可控的意外」意味着系统得知道
**这个用户**觉得什么算好意外。没有这一环，打分里的标签维度就是个常数，
反馈按钮点了也不会改变任何后续结果 —— 台上被问「点了喜欢之后呢」会答不上来。

存储是进程内的，和 `api.py` 的收藏一样：演示够用，重启即失。
"""

import threading


# 高德 type 串（`餐饮服务;咖啡厅;咖啡厅`）粒度太细，直接按它统计学不到东西：
# 「咖啡厅」和「咖啡馆」会被当成两类。归并到下面这组粗类目再统计。
# 顺序有意义：从具体到宽泛，第一个命中的关键词决定类目。
TAG_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("咖啡", "咖啡"),
    ("茶", "茶饮"),
    ("甜品", "甜品"),
    ("面包", "烘焙"),
    ("蛋糕", "烘焙"),
    ("海鲜", "海鲜"),
    ("烧烤", "烧烤"),
    ("火锅", "火锅"),
    ("快餐", "小馆"),
    ("小吃", "小馆"),
    ("餐饮", "餐饮"),
    ("风景", "风景"),
    ("公园", "风景"),
    ("广场", "风景"),
    ("海滨", "风景"),
    ("博物", "人文"),
    ("展览", "人文"),
    ("美术", "人文"),
    ("书店", "人文"),
    ("文化", "人文"),
    ("购物", "购物"),
    ("商场", "购物"),
)

# 认不出关键词、且 type 串也给不出大类时的最后兜底。
# 注意它**不再**是所有未知类型的共享桶：见 `_unknown_tag`。
UNKNOWN_TAG = "其它"

# 宽泛父类目：只有在没命中任何具体子类目时才用它兜底。
# 原因见 `tags_for_type` 的 docstring —— 同时记父类目会让反馈渗到兄弟类目上。
BROAD_TAGS = frozenset({"餐饮", "购物"})


def _unknown_tag(poi_type: str) -> str:
    """给认不出的 type 串一个**属于它自己**的桶，而不是所有未知类型共用一个。

    高德的 type 串是「大类;中类;小类」，取第一段就是它的大类
    （`体育休闲服务;度假疗养场所;度假疗养场所` -> `体育休闲服务`）。

    为什么不能共用一个「其它」：那样「其它」就变成了修复前的「餐饮」——
    一个共享桶。实测按高德真实分类打表，共用时「其它」横跨 7 个互不相关的
    大类（体育休闲、医疗保健、住宿、生活服务、商务住宅、交通设施、金融保险），
    于是点一次「不喜欢」某个度假场所，药店、酒店、电影院会一起沉底。
    按大类分桶后每个桶只含一个大类，反馈仍然落得下去，但只影响同一类。
    """
    head = poi_type.split(";", 1)[0].strip()
    return head or UNKNOWN_TAG


def tags_for_type(poi_type) -> list[str]:
    """高德 type 串 -> 粗类目列表。

    命中了具体子类目就**不再**记宽泛父类目。`餐饮服务;咖啡厅` 只算「咖啡」，
    不算「餐饮」—— 否则点一次「不喜欢」这家咖啡店会写入 `餐饮: -1`，
    而这个负分会渗到从来没被反馈过的海鲜酒楼和烧烤店上（各 -0.167）。
    父类目把兄弟类目一起拖下去，正好答错演示时那个问题：「点了不喜欢之后呢」。

    这也是上面 TAG_KEYWORDS 那条注释本来就写的规则（「从具体到宽泛，
    第一个命中的关键词决定类目」），之前只是没落到代码里。

    一个关键词都命中不了时不返回空列表 —— 空列表会让「不喜欢」的反馈无处落地，
    用户点了「一般」却什么都没记住。改为按 type 串的大类单独成桶（见 `_unknown_tag`），
    而不是所有未知类型共用一个「其它」：共享桶是本函数修过的同一个 bug。
    """
    if not isinstance(poi_type, str) or not poi_type.strip():
        return [UNKNOWN_TAG]

    specific: list[str] = []
    broad: list[str] = []
    for keyword, tag in TAG_KEYWORDS:
        if keyword not in poi_type:
            continue
        bucket = broad if tag in BROAD_TAGS else specific
        if tag not in bucket:
            bucket.append(tag)

    # 具体类目优先；`餐饮服务;餐馆` 这种只命中父类目的仍然落到「餐饮」上，
    # 不会退化成未知桶。
    return specific or broad or [_unknown_tag(poi_type)]


class PreferenceManager:
    """按类目累计正负反馈，给出 [-1, 1] 的偏好强度。

    线程安全：FastAPI 的同步路由跑在线程池里，而 recommend 内部还会开线程池
    并发评估候选，读写会真的并发发生。
    """

    # 单个类目的计数上限。不设上限的话连点十次「一般」会让这个类目永久沉底，
    # 演示时改主意（再点「还不错」）需要点同样多次才能翻回来。
    MAX_MAGNITUDE = 3

    def __init__(self):
        self._lock = threading.Lock()
        self._mode = "+5"
        self._scores: dict[str, int] = {}

    # ---------- 模式 ----------

    def set_mode(self, mode: str) -> None:
        with self._lock:
            self._mode = mode

    def get_mode(self) -> str:
        with self._lock:
            return self._mode

    # ---------- 反馈 ----------

    def record_feedback(self, liked: bool, pois: list | None = None, mode: str | None = None) -> list[str]:
        """记一次反馈，返回本次受影响的类目。

        `pois` 传的是**这次被推荐的** POI（前端反馈时回传路线里的 pois）。
        没有 POI 就没有可归因的类目 —— 只记 mode，不动任何计数：
        瞎猜一个类目比不记更糟，会把打分推向用户没表达过的方向。
        """
        delta = 1 if liked else -1
        affected: list[str] = []

        for poi in pois or []:
            if not isinstance(poi, dict):
                continue
            for tag in tags_for_type(poi.get("type")):
                if tag not in affected:
                    affected.append(tag)

        with self._lock:
            if isinstance(mode, str) and mode:
                self._mode = mode
            for tag in affected:
                current = self._scores.get(tag, 0) + delta
                self._scores[tag] = max(-self.MAX_MAGNITUDE, min(self.MAX_MAGNITUDE, current))

        return affected

    def affinity(self, poi_type) -> float:
        """这个 POI 类型的偏好强度，[-1, 1]。没有相关反馈时返回 0.0（中性）。

        一个 type 串可能落在多个类目上（`餐饮服务;咖啡厅` -> 餐饮 + 咖啡）。
        取**平均**而不是取最大：只按最喜欢的那个类目算，会让「喜欢咖啡但不喜欢
        餐饮」的用户拿到满分的餐饮推荐。
        """
        tags = tags_for_type(poi_type)
        with self._lock:
            values = [self._scores.get(tag, 0) for tag in tags]

        if not values:
            return 0.0
        return sum(values) / (len(values) * self.MAX_MAGNITUDE)

    # ---------- 自省（供 /api/preference 与测试用） ----------

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(self._scores)

    def reset(self) -> None:
        with self._lock:
            self._scores.clear()
            self._mode = "+5"
