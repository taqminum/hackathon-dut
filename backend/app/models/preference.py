class PreferenceManager:
    def __init__(self):
        self._mode = "+5"
        self._tags: list[str] = []

    def set_mode(self, mode: str):
        self._mode = mode

    def get_mode(self) -> str:
        return self._mode

    def set_tags(self, tags: list[str]):
        self._tags = tags

    def get_tags(self) -> list[str]:
        return list(self._tags)
