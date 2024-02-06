import json
import os
import subprocess
import platform
import time
import threading

from ..core.utils.system_debug_info import system_info
from .utils.local_storage_path import get_storage_path
from .utils.count_tokens import count_messages_tokens
from .utils.display_markdown_message import display_markdown_message


def handle_undo(self, arguments):
    # Removes all messages after the most recent user entry (and the entry itself).
    # Therefore user can jump back to the latest point of conversation.
    # Also gives a visual representation of the messages removed.

    if len(self.messages) == 0:
        return
    # Find the index of the last 'role': 'user' entry
    last_user_index = None
    for i, message in enumerate(self.messages):
        if message.get("role") == "user":
            last_user_index = i

    removed_messages = []

    # Remove all messages after the last 'role': 'user'
    if last_user_index is not None:
        removed_messages = self.messages[last_user_index:]
        self.messages = self.messages[:last_user_index]

    print("")  # Aesthetics.

    # Print out a preview of what messages were removed.
    for message in removed_messages:
        if "content" in message and message["content"] != None:
            display_markdown_message(
                f"**Removed message:** `\"{message['content'][:30]}...\"`"
            )
        elif "function_call" in message:
            display_markdown_message(
                f"**Removed codeblock**"
            )  # TODO: Could add preview of code removed here.

    print("")  # Aesthetics.


def handle_help(self, arguments):
    commands_description = {
        "%% [commands]": "Run commands in system shell",
        "%verbose [true/false]": "Toggle verbose mode. Without arguments or with 'true', it enters verbose mode. With 'false', it exits verbose mode.",
        "%reset": "Resets the current session.",
        "%undo": "Remove previous messages and its response from the message history.",
        "%save_message [path]": "Saves messages to a specified JSON path. If no path is provided, it defaults to 'messages.json'.",
        "%load_message [path]": "Loads messages from a specified JSON path. If no path is provided, it defaults to 'messages.json'.",
        "%tokens [prompt]": "EXPERIMENTAL: Calculate the tokens used by the next request based on the current conversation's messages and estimate the cost of that request; optionally provide a prompt to also calulate the tokens used by that prompt and the total amount of tokens that will be sent with the next request",
        "%edit": "Edit the previous code block",
        "%help": "Show this help message.",
        "%info": "Show system and interpreter information",
    }

    base_message = ["> **Available Commands:**\n\n"]

    # Add each command and its description to the message
    for cmd, desc in commands_description.items():
        base_message.append(f"- `{cmd}`: {desc}\n")

    additional_info = [
        "\n\nFor further assistance, please join our community Discord or consider contributing to the project's development."
    ]

    # Combine the base message with the additional info
    full_message = base_message + additional_info

    display_markdown_message("".join(full_message))


def handle_verbose(self, arguments=None):
    if arguments == "" or arguments == "true":
        display_markdown_message("> Entered verbose mode")
        print("\n\nCurrent messages:\n")
        for message in self.messages:
            message = message.copy()
            if message["type"] == "image" and message.get("format") != "path":
                message["content"] = (
                    message["content"][:30] + "..." + message["content"][-30:]
                )
            print(message, "\n")
        print("\n")
        self.verbose = True
    elif arguments == "false":
        display_markdown_message("> Exited verbose mode")
        self.verbose = False
    else:
        display_markdown_message("> Unknown argument to verbose command.")


def handle_info(self, arguments):
    system_info(self)


def handle_reset(self, arguments):
    self.reset()
    display_markdown_message("> Reset Done")


def default_handle(self, arguments):
    display_markdown_message("> Unknown command")
    handle_help(self, arguments)


def handle_save_message(self, json_path):
    if json_path == "":
        json_path = "messages.json"
    if not json_path.endswith(".json"):
        json_path += ".json"
    with open(json_path, "w") as f:
        json.dump(self.messages, f, indent=2)

    display_markdown_message(f"> messages json export to {os.path.abspath(json_path)}")


def handle_load_message(self, json_path):
    if json_path == "":
        json_path = "messages.json"
    if not json_path.endswith(".json"):
        json_path += ".json"
    with open(json_path, "r") as f:
        self.messages = json.load(f)

    display_markdown_message(
        f"> messages json loaded from {os.path.abspath(json_path)}"
    )

def edit_code_block(self, arguments):
    # Find the index of the last code
    last_code_block = None
    for i, message in enumerate(self.messages):
        if message.get("type") == "code":
            last_code_block = i
    
    message_to_edit = []

    # Extract the message
    if last_code_block is not None:
        message_to_edit = self.messages[last_code_block]
        self.messages = self.messages[:last_code_block]
    
    # Save the file
    temp_filename = "editing_text_block"
    file_path = get_storage_path() + "/" + temp_filename
    with open(file_path, 'w') as file:
        file.write(message_to_edit['content'])

    # Open the file in users preferred editor
    if platform.system() == 'Windows':
        os.startfile(file_path)
    elif platform.system() == 'Darwin':
        subprocess.run(['open', file_path])
    else:
        subprocess.run(['xdg-open', file_path])
        
    # Function to get the last modified time of a file
    def get_file_last_modified_time(file_path):
        return os.path.getmtime(file_path)

    # Function to monitor file changes
    def monitor_file_changes(file_path, interval=1):
        last_modified_time = get_file_last_modified_time(file_path)

        while not stop_monitoring.is_set():
            time.sleep(interval)
            current_modified_time = get_file_last_modified_time(file_path)
            if current_modified_time != last_modified_time:
                print(f"Code has been editted successfully")
                last_modified_time = current_modified_time

    # Thread stop flag
    stop_monitoring = threading.Event()

    # Create and start the monitoring thread
    monitoring_thread = threading.Thread(target=monitor_file_changes, args=(file_path,))
    monitoring_thread.start()

    print("Monitoring file changes. Press Enter to continue.")
    input()  # Wait for Enter key press
    stop_monitoring.set()  # Signal to stop the monitoring thread

    # Wait for the monitoring thread to finish
    monitoring_thread.join()
    print("Code edit submitted.")

    
    with open(file_path, "r") as f:
        print(f)
        message_to_edit['content'] = f.read()
        self.messages.append(message_to_edit)

    print(message_to_edit)
    print(dir(self))
    self._respond_and_store()

def handle_count_tokens(self, prompt):
    messages = [{"role": "system", "message": self.system_message}] + self.messages

    outputs = []

    if len(self.messages) == 0:
        (conversation_tokens, conversation_cost) = count_messages_tokens(
            messages=messages, model=self.llm.model
        )
    else:
        (conversation_tokens, conversation_cost) = count_messages_tokens(
            messages=messages, model=self.llm.model
        )

    outputs.append(
        (
            f"> Tokens sent with next request as context: {conversation_tokens} (Estimated Cost: ${conversation_cost})"
        )
    )

    if prompt:
        (prompt_tokens, prompt_cost) = count_messages_tokens(
            messages=[prompt], model=self.llm.model
        )
        outputs.append(
            f"> Tokens used by this prompt: {prompt_tokens} (Estimated Cost: ${prompt_cost})"
        )

        total_tokens = conversation_tokens + prompt_tokens
        total_cost = conversation_cost + prompt_cost

        outputs.append(
            f"> Total tokens for next request with this prompt: {total_tokens} (Estimated Cost: ${total_cost})"
        )

    outputs.append(
        f"**Note**: This functionality is currently experimental and may not be accurate. Please report any issues you find to the [Open Interpreter GitHub repository](https://github.com/KillianLucas/open-interpreter)."
    )

    display_markdown_message("\n".join(outputs))


def handle_magic_command(self, user_input):
    # Handle shell
    if user_input.startswith("%%"):
        code = user_input[2:].strip()
        self.computer.run("shell", code, stream=True, display=True)
        print("")
        return

    # split the command into the command and the arguments, by the first whitespace
    switch = {
        "help": handle_help,
        "verbose": handle_verbose,
        "reset": handle_reset,
        "save_message": handle_save_message,
        "load_message": handle_load_message,
        "edit": edit_code_block,
        "undo": handle_undo,
        "tokens": handle_count_tokens,
        "info": handle_info,
    }

    user_input = user_input[1:].strip()  # Capture the part after the `%`
    command = user_input.split(" ")[0]
    arguments = user_input[len(command) :].strip()

    if command == "debug":
        print(
            "\n`%debug` / `--debug_mode` has been renamed to `%verbose` / `--verbose`.\n"
        )
        time.sleep(1.5)
        command = "verbose"

    action = switch.get(
        command, default_handle
    )  # Get the function from the dictionary, or default_handle if not found
    action(self, arguments)  # Execute the function
