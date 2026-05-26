def run_search(
    query: str | None = None,
    model_id: int | None = None,
    topk: int = 10,
) -> None:
    if model_id is None:
        print(
            "[INFO] No model_id specified. "
            "Use --model-id to select an embedding model."
        )
        return

    if not query:
        print("[INFO] No query provided. Provide a text query or audio file path.")
        return

    print("[INFO] Semantic search requires a real embedding backend (CLAP).")
    print("[INFO] Install torch + transformers and use 'sample-brain embed --backend clap' first.")
    print("[INFO] Index/search contracts are available in src.index for NumPy-based search.")
    print("[INFO] Once embeddings exist and an index is built, search will return ranked results.")
    print(f"[INFO] Requested: query='{query}', model_id={model_id}, topk={topk}")
