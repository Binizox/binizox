__all__ = ["select_model", "select_embedding_model", "get_embedding_model_info_by_id"]


def __getattr__(name: str):
    if name == "select_model":
        from binizox.models.chat import select_model

        return select_model

    if name in {"select_embedding_model", "get_embedding_model_info_by_id"}:
        from binizox.models.embed import get_embedding_model_info_by_id, select_embedding_model

        return {
            "select_embedding_model": select_embedding_model,
            "get_embedding_model_info_by_id": get_embedding_model_info_by_id,
        }[name]

    raise AttributeError(f"module 'binizox.models' has no attribute {name!r}")


def __dir__():
    return sorted(set(globals()) | set(__all__))
