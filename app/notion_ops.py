from typing import List, Dict, Any
from notion_client import Client


def find_notion_database(notion: Client, database_id: str) -> dict:
    return notion.databases.retrieve(database_id=database_id)


def build_notion_database_options(notion: Client, payload: dict) -> List[Dict[str, Any]]:
    databases = []
    query = payload.get("value")
    database_filter = {"property": "object", "value": "database"}
    cursor = None
    first_page = notion.search(query=query, filter=database_filter, start_cursor=cursor)
    databases = databases + first_page["results"]
    cursor = first_page["next_cursor"]
    while cursor is not None:
        page = notion.search(query=query, filter=database_filter, start_cursor=cursor)
        databases = databases + page["results"]
        cursor = page["next_cursor"]

    options = []
    for database in databases:
        database_id = database["id"]
        database_name = database["title"][0]["plain_text"]
        options.append({"text": {"type": "plain_text", "text": database_name}, "value": database_id})
    return options


def _build_option(o: dict) -> dict:
    return {
        "text": {"type": "plain_text", "text": o["name"]},
        "value": o["id"],
    }


def build_input_blocks(database: dict) -> List[Dict[str, Any]]:
    blocks = []
    database_name = database["title"][0]["plain_text"][:24]
    blocks.append(
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f'You\'re going to send data to Notion database *"{database_name}"*',
            },
            "accessory": {
                "type": "button",
                "action_id": "go-back-to-database-select-view",
                "text": {"type": "plain_text", "text": "Select Database"},
                "value": "1",
            },
        },
    )
    title_key = list(filter(lambda p: p[1]["type"] == "title", database["properties"].items()))[0][0]
    title = database["properties"].pop(title_key)
    blocks.append(
        {
            "type": "input",
            "block_id": title["id"],
            "element": {"type": "plain_text_input", "action_id": "title"},
            "label": {"type": "plain_text", "text": title_key},
            "optional": False,
        }
    )
    for name, prop in database["properties"].items():
        prop_type = prop.get("type", "text")
        label = {"type": "plain_text", "text": name}
        block_id = prop.get("id", name)
        if prop_type == "select" and len(prop["select"]["options"]) > 0:
            blocks.append(
                {
                    "type": "input",
                    "block_id": block_id,
                    "element": {
                        "type": "static_select",
                        "options": [_build_option(o) for o in prop["select"]["options"]],
                        "action_id": prop_type,
                    },
                    "label": label,
                    "optional": True,
                }
            )
        elif prop_type == "multi_select" and len(prop["multi_select"]["options"]) > 0:
            blocks.append(
                {
                    "type": "input",
                    "block_id": block_id,
                    "element": {
                        "type": "multi_static_select",
                        "options": [_build_option(o) for o in prop["multi_select"]["options"]],
                        "action_id": prop_type,
                    },
                    "label": label,
                    "optional": True,
                }
            )
        elif prop_type == "rich_text":
            blocks.append(
                {
                    "type": "input",
                    "block_id": block_id,
                    "element": {"type": "plain_text_input", "multiline": True, "action_id": prop_type},
                    "label": label,
                    "optional": True,
                }
            )
        elif prop_type in ("number", "url", "email", "phone_number"):
            blocks.append(
                {
                    "type": "input",
                    "block_id": block_id,
                    "element": {"type": "plain_text_input", "action_id": prop_type},
                    "label": label,
                    "optional": True,
                }
            )
        elif prop_type == "date":
            blocks.append(
                {
                    "type": "input",
                    "block_id": block_id,
                    "element": {"type": "datepicker", "action_id": prop_type},
                    "label": label,
                    "optional": True,
                }
            )
        elif prop_type == "checkbox":
            blocks.append(
                {
                    "type": "input",
                    "block_id": block_id,
                    "element": {
                        "type": "checkboxes",
                        "options": [
                            {
                                "text": {"type": "plain_text", "text": " "},
                                "description": {"type": "plain_text", "text": "This will be synchronized in Notion"},
                                "value": "checked",
                            }
                        ],
                        "action_id": prop_type,
                    },
                    "label": label,
                    "optional": True,
                }
            )

        # The following ones are not yet supported
        # people
        # relation
        # formula
        # rollup
        # files

    return blocks


def to_page_properties(state_values: dict) -> dict:
    properties = {}
    for block_id, v in state_values.items():
        action_id = list(v.keys())[0]
        if action_id == "title":
            properties[block_id] = {"title": [{"type": "text", "text": {"content": v[action_id]["value"]}}]}
        elif action_id == "select" and v[action_id].get("selected_option") is not None:
            properties[block_id] = {"select": {"id": v[action_id]["selected_option"]["value"]}}
        elif action_id == "multi_select" and v[action_id].get("selected_options") is not None:
            selected_options = [{"id": o["value"]} for o in v[action_id]["selected_options"]]
            properties[block_id] = {"multi_select": selected_options}
        elif action_id == "rich_text" and v[action_id].get("value") is not None:
            properties[block_id] = {"rich_text": [{"text": {"content": v[action_id]["value"]}}]}
        elif action_id == "number" and v[action_id].get("value") is not None:
            properties[block_id] = {"number": int(v[action_id]["value"])}
        elif action_id == "date" and v[action_id].get("selected_date") is not None:
            properties[block_id] = {"date": {"start": v[action_id]["selected_date"]}}
        elif action_id == "checkbox" and v[action_id].get("selected_options") is not None:
            properties[block_id] = {"checkbox": len(v[action_id]["selected_options"]) > 0}
        elif action_id == "url" and v[action_id].get("value") is not None:
            properties[block_id] = {"url": v[action_id]["value"]}
        elif action_id == "email" and v[action_id].get("value") is not None:
            properties[block_id] = {"email": v[action_id]["value"]}
        elif action_id == "phone_number" and v[action_id].get("value") is not None:
            properties[block_id] = {"phone_number": v[action_id]["value"]}
    return properties


def send_to_notion(notion: Client, database_id: str, state_values: dict):
    new_page = notion.pages.create(
        parent={"type": "database_id", "database_id": database_id},
        properties=to_page_properties(state_values),
    )
    return new_page
