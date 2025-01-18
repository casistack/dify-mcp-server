import asyncio
import os
from pathlib import Path
from typing import Dict, Any

from src.dify_mcp_server.server import (
    DifyAPI,
    Server,
    InitializationOptions,
    NotificationOptions,
)
import mcp.types as types


# Initialize server and API
def init_server():
    """Initialize the server and API with proper configuration"""
    # Find config.yaml in the current directory or parent directories
    current_dir = Path.cwd()
    config_path = None

    # Search for config.yaml in current and parent directories
    search_dirs = [current_dir] + list(current_dir.parents)
    for directory in search_dirs:
        potential_config = directory / "config.yaml"
        if potential_config.exists():
            config_path = str(potential_config)
            break

    if not config_path:
        raise ValueError("config.yaml not found in current or parent directories")

    print(f"Using config file: {config_path}")

    # Set environment variable for the server
    os.environ["CONFIG_PATH"] = config_path

    # Initialize server
    server = Server("dify_mcp_server")
    dify_api = DifyAPI(config_path)

    return server, dify_api


# Initialize server and API globally
server, dify_api = init_server()


async def test_tool_listing():
    """Test listing of available tools"""
    print("\n=== Testing Tool Listing ===")
    tools = []

    # Get tools using the same logic as handle_list_tools
    print("Listing available tools...")

    for i, app_info in enumerate(dify_api.dify_app_infos):
        try:
            app_param = dify_api.dify_app_params[i]
            app_type = app_info.get("type", "unknown")

            print(f"Processing {app_info['name']} ({app_type})")

            # Create input schema
            inputSchema = dict(
                type="object",
                properties={},
                required=[],
            )

            if "user_input_form" in app_param:
                for param in app_param["user_input_form"]:
                    param_type = list(param.keys())[0]
                    param_info = param[param_type]
                    property_name = param_info["variable"]
                    inputSchema["properties"][property_name] = dict(
                        type=param_type,
                        description=param_info["label"],  # Use original label
                    )
                    if param_info.get("required", False):
                        inputSchema["required"].append(property_name)

            # Create tool using only the app name for display
            tool = types.Tool(
                name=app_info["name"],  # Use only the app name for display
                description=app_info.get("description", "No description available"),
                inputSchema=inputSchema,
            )
            tools.append(tool)
            print(f"Successfully added tool: {app_info['name']}")

        except Exception as e:
            print(f"Error processing tool {app_info['name']}: {str(e)}")
            if hasattr(e, "__context__"):
                print(f"Context: {str(e.__context__)}")
            continue

    assert len(tools) > 0, "No tools found"

    print(f"\nFound {len(tools)} tools:")
    for tool in tools:
        print(f"\nTool: {tool.name}")
        print(f"Description: {tool.description}")
        print("Parameters:")
        for param_name, param_info in tool.inputSchema.get("properties", {}).items():
            print(f"  - {param_name}: {param_info.get('description', '')}")
            if "enum" in param_info:
                print(f"    Options: {', '.join(param_info['enum'])}")

    return tools


async def test_football_agent():
    """Test Football Intelligence Agent"""
    print("\n=== Testing Football Intelligence Agent ===")

    # First get the tool info to see available options
    tools = await test_tool_listing()
    football_tool = next((t for t in tools if "Football" in t.name), None)

    if not football_tool:
        print("Football Intelligence Agent not found in tools")
        return False

    # Print available options for each parameter
    print("\nAvailable parameter options:")
    for param_name, param_info in football_tool.inputSchema.get(
        "properties", {}
    ).items():
        print(f"\n{param_name}:")
        print(f"Description: {param_info.get('description', '')}")
        if "enum" in param_info:
            print(f"Valid values: {param_info['enum']}")

    # Test cases
    test_cases = [
        {
            "name": "Valid parameters",
            "params": {
                "league": "Premier League",
                "entity": "Manchester United",
                "query_type": "Team Information",
                "time_frame": "Current Season",
            },
            "should_succeed": True,
        },
        {
            "name": "Invalid time_frame",
            "params": {
                "league": "Premier League",
                "entity": "Manchester United",
                "query_type": "Team Information",
                "time_frame": "Last Week",  # Invalid value
            },
            "should_succeed": False,
        },
    ]

    success = True
    for test_case in test_cases:
        print(f"\nTesting case: {test_case['name']}")
        print(f"Parameters: {test_case['params']}")

        try:
            # Set the current app to the football agent
            app_index = next(
                (
                    i
                    for i, info in enumerate(dify_api.dify_app_infos)
                    if "Football" in info["name"]
                ),
                None,
            )
            if app_index is not None:
                dify_api.set_current_app(app_index)

                # Get responses
                responses = dify_api.chat_message(
                    inputs=test_case["params"], response_mode="streaming"
                )
                print("\nResponse received:")
                for res in responses:
                    if (
                        "event" in res
                        and res["event"] == "agent_message"
                        and "answer" in res
                    ):
                        print(res["answer"])

                if not test_case["should_succeed"]:
                    print("Error: Test case should have failed but succeeded")
                    success = False

        except Exception as e:
            if test_case["should_succeed"]:
                print(f"Error: Test case should have succeeded but failed: {str(e)}")
                if hasattr(e, "response") and hasattr(e.response, "json"):
                    try:
                        error_details = e.response.json()
                        print(f"Error details: {error_details}")
                    except:
                        pass
                success = False
            else:
                print(f"Expected error received: {str(e)}")

    return success


async def test_travel_consultant():
    """Test Travel Consultant"""
    print("\n=== Testing Travel Consultant UK ===")

    # First get the tool info to see available options
    tools = await test_tool_listing()
    travel_tool = next((t for t in tools if "Travel" in t.name), None)

    if not travel_tool:
        print("Travel Consultant not found in tools")
        return False

    # Print available options for each parameter
    print("\nAvailable parameter options:")
    for param_name, param_info in travel_tool.inputSchema.get("properties", {}).items():
        print(f"\n{param_name}:")
        print(f"Description: {param_info.get('description', '')}")
        if "enum" in param_info:
            print(f"Valid values: {param_info['enum']}")

    # Test cases
    test_cases = [
        {
            "name": "Valid parameters",
            "params": {
                "destination": "London",
                "num_day": "5",
                "budget": "Below £1,000. ",  # Note the trailing space
            },
            "should_succeed": True,
        },
        {
            "name": "Invalid budget format",
            "params": {
                "destination": "London",
                "num_day": "5",
                "budget": "1000",  # Invalid format
            },
            "should_succeed": False,
        },
    ]

    success = True
    for test_case in test_cases:
        print(f"\nTesting case: {test_case['name']}")
        print(f"Parameters: {test_case['params']}")

        try:
            # Set the current app to the travel consultant
            app_index = next(
                (
                    i
                    for i, info in enumerate(dify_api.dify_app_infos)
                    if "Travel" in info["name"]
                ),
                None,
            )
            if app_index is not None:
                dify_api.set_current_app(app_index)

                # Get responses
                responses = dify_api.chat_message(
                    inputs=test_case["params"], response_mode="streaming"
                )
                print("\nResponse received:")
                for res in responses:
                    if (
                        "event" in res
                        and res["event"] == "agent_message"
                        and "answer" in res
                    ):
                        print(res["answer"])

                if not test_case["should_succeed"]:
                    print("Error: Test case should have failed but succeeded")
                    success = False

        except Exception as e:
            if test_case["should_succeed"]:
                print(f"Error: Test case should have succeeded but failed: {str(e)}")
                if hasattr(e, "response") and hasattr(e.response, "json"):
                    try:
                        error_details = e.response.json()
                        print(f"Error details: {error_details}")
                    except:
                        pass
                success = False
            else:
                print(f"Expected error received: {str(e)}")

    return success


async def main():
    """Main test function"""
    print("Starting MCP Tool Tests...")

    # First test tool listing
    await test_tool_listing()

    # Test each tool
    football_result = await test_football_agent()
    travel_result = await test_travel_consultant()

    # Print summary
    print("\n=== Test Summary ===")
    print(f"Football Agent Test: {'PASSED' if football_result else 'FAILED'}")
    print(f"Travel Consultant Test: {'PASSED' if travel_result else 'FAILED'}")


if __name__ == "__main__":
    asyncio.run(main())
