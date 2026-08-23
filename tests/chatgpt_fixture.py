import json
from pathlib import Path


def create_chatgpt_fixture(root: str | Path, count: int = 1100) -> Path:
    root_path = Path(root)
    data_directory = root_path / "500" / "llama32-chat" / "data"
    knowledge_directory = data_directory / "local_knowledge"
    knowledge_directory.mkdir(parents=True, exist_ok=True)

    conversations = []
    for index in range(count):
        conversations.append(
            {
                "id": f"synthetic-{index}",
                "title": f"合成對話 {index}",
                "create_time": 1_700_000_000 + index,
                "mapping": {
                    f"user-{index}": {
                        "message": {
                            "author": {"role": "user"},
                            "content": {"parts": [f"履歷與對話測試 {index}"]},
                        }
                    },
                    f"assistant-{index}": {
                        "message": {
                            "author": {"role": "assistant"},
                            "content": {"parts": [f"合成回答 {index}"]},
                        }
                    },
                },
            }
        )

    database_path = knowledge_directory / "complete_chatgpt_database.json"
    database_path.write_text(
        json.dumps(
            {"data": {"conversations": conversations}},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (data_directory / "conversations.json").write_text(
        json.dumps(
            [
                {
                    "id": "synthetic-legacy",
                    "timestamp": "2024-01-01T00:00:00Z",
                    "user_input": "舊版合成記憶",
                    "assistant_response": "舊版合成回答",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (knowledge_directory / "complete_data_index.json").write_text(
        json.dumps(
            {
                "data_types": {
                    "conversations": {"count": count},
                    "messages": {"count": count * 2},
                    "group_chats": {"count": 0},
                    "shared_conversations": {"count": 0},
                    "sora_generations": {"count": 0},
                    "dalle_generations": {"count": 0},
                    "attachments": {"count": 0},
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return database_path
