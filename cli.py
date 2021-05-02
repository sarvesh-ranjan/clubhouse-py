"""
cli.py

Sample CLI Clubhouse Client

RTC: For voice communication
"""

import os
import sys
import threading
import configparser
import keyboard
import sys
import time
import colorama
from colorama import Fore, Style
from rich.table import Table
from rich.console import Console
from clubhouse.clubhouse import Clubhouse

# Set some global variables
try:
    import agorartc
    RTC = agorartc.createRtcEngineBridge()
    eventHandler = agorartc.RtcEngineEventHandlerBase()
    RTC.initEventHandler(eventHandler)
    # 0xFFFFFFFE will exclude Chinese servers from Agora's servers.
    RTC.initialize(Clubhouse.AGORA_KEY, None, agorartc.AREA_CODE_GLOB & 0xFFFFFFFE)
    # Enhance voice quality
    if RTC.setAudioProfile(
            agorartc.AUDIO_PROFILE_MUSIC_HIGH_QUALITY_STEREO,
            agorartc.AUDIO_SCENARIO_GAME_STREAMING
        ) < 0:
        print("[-] Failed to set the high quality audio profile")
except ImportError:
    RTC = None

def set_interval(interval):
    """ (int) -> decorator

    set_interval decorator
    """
    def decorator(func):
        def wrap(*args, **kwargs):
            stopped = threading.Event()
            def loop():
                while not stopped.wait(interval):
                    ret = func(*args, **kwargs)
                    if not ret:
                        break
            thread = threading.Thread(target=loop)
            thread.daemon = True
            thread.start()
            return stopped
        return wrap
    return decorator

def write_config(user_id, user_token, user_device, filename='setting.ini'):
    """ (str, str, str, str) -> bool

    Write Config. return True on successful file write
    """
    config = configparser.ConfigParser()
    config["Account"] = {
        "user_device": user_device,
        "user_id": user_id,
        "user_token": user_token,
    }
    with open(filename, 'w') as config_file:
        config.write(config_file)
    return True

def read_config(filename='setting.ini'):
    """ (str) -> dict of str

    Read Config
    """
    config = configparser.ConfigParser()
    config.read(filename)
    if "Account" in config:
        return dict(config['Account'])
    return dict()

def process_onboarding(client):
    """ (Clubhouse) -> NoneType

    This is to process the initial setup for the first time user.
    """
    print("=" * 30)
    print("Welcome to Clubhouse!\n")
    print("The registration is not yet complete.")
    print("Finish the process by entering your legal name and your username.")
    print("WARNING: THIS FEATURE IS PURELY EXPERIMENTAL.")
    print("         YOU CAN GET BANNED FOR REGISTERING FROM THE CLI ACCOUNT.")
    print("=" * 30)

    while True:
        user_realname = input("[.] Enter your legal name (John Smith): ")
        user_username = input("[.] Enter your username (elonmusk1234): ")

        user_realname_split = user_realname.split(" ")

        if len(user_realname_split) != 2:
            print("[-] Please enter your legal name properly.")
            continue

        if not (user_realname_split[0].isalpha() and
                user_realname_split[1].isalpha()):
            print("[-] Your legal name is supposed to be written in alphabets only.")
            continue

        if len(user_username) > 16:
            print("[-] Your username exceeds above 16 characters.")
            continue

        if not user_username.isalnum():
            print("[-] Your username is supposed to be in alphanumerics only.")
            continue

        client.update_name(user_realname)
        result = client.update_username(user_username)
        if not result['success']:
            print(f"[-] You failed to update your username. ({result})")
            continue

        result = client.check_waitlist_status()
        if not result['success']:
            print("[-] Your registration failed.")
            print(f"    It's better to sign up from a real device. ({result})")
            continue

        print("[-] Registration Complete!")
        print("    Try registering by real device if this process pops again.")
        break

def print_channel_list(client, max_limit=2000):
    """ (Clubhouse) -> NoneType

    Print list of channels
    """
    # Get channels and print out

    console = Console()
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("#")
    table.add_column("channel", style="cyan", justify="left")
    table.add_column("topic", justify="left")
    table.add_column("club_name", justify="left")
    table.add_column("co", justify="left")
    table.add_column("speakers", justify="left")
    channels = client.get_channels()['channels']
    i = 1
    for channel in channels:

        users = channel["users"]
        speakers = ""
        for user in users:
            if user['is_speaker'] or user['is_moderator']:
                if speakers == "":
                    speakers += user["name"]
                else:
                    speakers += "," + user["name"]


        _option = ""
        _option += "\xEE\x85\x84" if channel['is_social_mode'] or channel['is_private'] else ""
        clubInfo = channel['club']
        clubName = "----------"

        if clubInfo:
            clubName = clubInfo['name']
        if i%2 == 0:
            table.add_row(
                '[cyan]'+str(i),
                # '[cyan]'+str(_option),
                '[cyan]'+str(channel['channel']),
                '[cyan]'+str(channel['topic']),
                '[cyan]'+str(clubName),
                '[cyan]'+str(channel['num_speakers']),
                '[cyan]'+str(speakers),
            )

        else:
            table.add_row(
                '[orange1]'+str(i),
                # '[orange1]'+str(_option),
                '[orange1]'+str(channel['channel']),
                '[orange1]'+str(channel['topic']),
                '[orange1]'+str(clubName),
                '[orange1]'+str(channel['num_speakers']),
                '[orange1]'+str(speakers),
            )
        i+=1

    console.print(table)


def chat_main(client):
    """ (Clubhouse) -> NoneType

    Main function for chat
    """
    max_limit = 2000
    channel_speaker_permission = False
    _wait_func = None
    _ping_func = None

    def _request_speaker_permission(client, channel_name, user_id):
        """ (str) -> bool

        Raise hands for permissions
        """
        if not channel_speaker_permission:
            client.audience_reply(channel_name, True, False)
            _wait_func = _wait_speaker_permission(client, channel_name, user_id)
            print("[/] You've raised your hand. Wait for the moderator to give you the permission.")

    @set_interval(30)
    def _ping_keep_alive(client, channel_name):
        """ (str) -> bool

        Continue to ping alive every 30 seconds.
        """
        client.active_ping(channel_name)
        return True

    @set_interval(10)
    def _wait_speaker_permission(client, channel_name, user_id):
        """ (str) -> bool

        Function that runs when you've requested for a voice permission.
        """
        # Get some random users from the channel.
        _channel_info = client.get_channel(channel_name)
        if _channel_info['success']:
            for _user in _channel_info['users']:
                if _user['user_id'] != user_id:
                    user_id = _user['user_id']
                    break
            # Check if the moderator allowed your request.
            res_inv = client.accept_speaker_invite(channel_name, user_id)
            if res_inv['success']:
                print("[-] Now you have a speaker permission.")
                print("    Please re-join this channel to activate a permission.")
                return False
        return True

    while True:
        # Choose which channel to enter.
        # Join the talk on success.
        user_id = client.HEADERS.get("CH-UserID")
        print_channel_list(client, max_limit)
        channel_name = input("[.] Enter channel_name: ")
        channel_info = client.join_channel(channel_name)
        if not channel_info['success']:
            # Check if this channel_name was taken from the link
            channel_info = client.join_channel(channel_name, "link", "e30=")
            if not channel_info['success']:
                print(f"[-] Error while joining the channel ({channel_info['error_message']})")
                continue



        # Check for the voice level.
        if RTC:
            token = channel_info['token']
            RTC.joinChannel(token, channel_name, "", int(user_id))
        else:
            print("[!] Agora SDK is not installed.")
            print("    You may not speak or listen to the conversation.")

        # Activate pinging
        client.active_ping(channel_name)
        _ping_func = _ping_keep_alive(client, channel_name)
        _wait_func = None

        print_users(channel_info, user_id, client)
        print_channel_list(client, max_limit)

        users = channel_info['users']
        number_of_users = len(users)

        print(Fore.GREEN + "______________________________Joined Channel_____________________________\n")
        print("Channel: -> ")
        print("ChannelID: ", channel_info['channel_id'], " ChannelName: ", channel_info['channel'])
        print("Topic: ", channel_info['topic'])
        print(Fore.CYAN)

        clubInfo = channel_info['club']
        clubID = "----------"
        clubName = "----------"
        clubDescription = "----------"
        if clubInfo:
            clubID = clubInfo['club_id']
            clubName = clubInfo['name']
            clubDescription = clubInfo['description']

        print("Club: -> ")
        print("ClubID: ", clubID, " ClubName: ", clubName)
        print("Description: ", clubDescription)
        print(Fore.YELLOW)
        print("\nNumber of Users: ", number_of_users)
        print("____________________________________________________________________________")
        print(Fore.RED)

        # Add raise_hands key bindings for speaker permission
        # Sorry for the bad quality
        if not channel_speaker_permission:

            if sys.platform == "darwin": # OSX
                _hotkey = "9"
            elif sys.platform == "win32": # Windows
                _hotkey = "ctrl+shift+h"

            print(f"[*] Press [{_hotkey}] to RAISE YOUR HAND for the speaker permission.")

            keyboard.add_hotkey(
                _hotkey,
                _request_speaker_permission,
                args=(client, channel_name, user_id),
                trigger_on_release=True,
            )

            _hotkey_refresh_users = "1"

            print(f"[*] Press [{_hotkey_refresh_users}] to refresh USERS in conversation.")

            keyboard.add_hotkey(
                _hotkey_refresh_users,
                print_users,
                args=(channel_info, user_id, client),
                trigger_on_release=True,
            )

            _hotkey_refresh_channels = "2"

            print(f"[*] Press [{_hotkey_refresh_channels}] to refresh CHANNELS in conversation.")

            keyboard.add_hotkey(
                _hotkey_refresh_channels,
                print_channel_list,
                args=(client, max_limit),
                trigger_on_release=True,
            )

        print(Fore.MAGENTA)
        input(f"[*] Press [Enter] to quit conversation.\n\t____________________\n\n")

        keyboard.unhook_all()

        # Safely leave the channel upon quitting the channel.
        if _ping_func:
            _ping_func.set()
        if _wait_func:
            _wait_func.set()
        if RTC:
            RTC.leaveChannel()
        client.leave_channel(channel_name)

def print_users(channel_info, user_id, client):
    users = channel_info['users']

    number_of_users = len(users)

    print(Fore.GREEN + "______________________________Joining Channel_______________________________\n")
    # print(channel_info)
    print("Channel: -> ")
    print("ChannelID: ", channel_info['channel_id'], " ChannelName: ", channel_info['channel'])
    print("Topic: ", channel_info['topic'])
    print(Fore.CYAN)

    clubInfo = channel_info['club']
    clubID = ""
    clubName = ""
    clubDescription = ""
    if clubInfo:
        clubID = clubInfo['club_id']
        clubName = clubInfo['name']
        clubDescription = clubInfo['description']

    print("Club: -> ")
    print("ClubID: ", clubID, " ClubName: ", clubName)
    print("Description: ", clubDescription)
    print(Fore.YELLOW, "\nNumber of Users: ", number_of_users)
    print("____________________________________________________________________________")
    print(Fore.RED)

    # List currently available users (TOP 20 only.)
    # Also, check for the current user's speaker permission.
    channel_speaker_permission = False
    console = Console()
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("#", style="cyan", justify="right")
    table.add_column("user_id")
    table.add_column("username")
    table.add_column("name")
    table.add_column("s-m")
    table.add_column("description")

    i = 1
    for user in users:
        is_speaker = user['is_speaker']
        if not is_speaker:
            is_speaker = "-"
        is_moderator = user['is_moderator']
        if not is_moderator:
            is_moderator = "-"

        desc = "----------"
        if user['is_speaker']:
            desc = client.get_profile(user['user_id'])['user_profile']['bio']

        is_speaker_mod = ""
        if is_speaker != "-":
            is_speaker_mod += "T"
        else:
            is_speaker_mod += "F"
        is_speaker_mod += "-"
        if is_moderator != "-":
            is_speaker_mod += "T"
        else:
            is_speaker_mod += "F"

        if desc == "":
            desc = "----------"

        if i%2 == 0:
            table.add_row(
                '[white]'+str(i),
                '[white]'+str(user['user_id']),
                '[white]'+str(user['name']),
                '[white]'+str(user['username']),
                '[white]'+str(is_speaker_mod),
                '[white]'+str(desc),
            )
        else:
            table.add_row(
                '[orange1]'+str(i),
                '[orange1]'+str(user['user_id']),
                '[orange1]'+str(user['name']),
                '[orange1]'+str(user['username']),
                '[orange1]'+str(is_speaker_mod),
                '[orange1]'+str(desc),
            )
        i+=1
        # Check if the user is the speaker
        if user['user_id'] == int(user_id):
            channel_speaker_permission = bool(user['is_speaker'])

        if i > 25:
            break
    console.print(table)

def user_authentication(client):
    """ (Clubhouse) -> NoneType

    Just for authenticating the user.
    """

    result = None
    while True:
        user_phone_number = input("[.] Please enter your phone number. (+818043217654) > ")
        result = client.start_phone_number_auth(user_phone_number)
        if not result['success']:
            print(f"[-] Error occured during authentication. ({result['error_message']})")
            continue
        break

    result = None
    while True:
        verification_code = input("[.] Please enter the SMS verification code (1234, 0000, ...) > ")
        result = client.complete_phone_number_auth(user_phone_number, verification_code)
        if not result['success']:
            print(f"[-] Error occured during authentication. ({result['error_message']})")
            continue
        break

    user_id = result['user_profile']['user_id']
    user_token = result['auth_token']
    user_device = client.HEADERS.get("CH-DeviceId")
    write_config(user_id, user_token, user_device)

    print("[.] Writing configuration file complete.")

    if result['is_waitlisted']:
        print("[!] You're still on the waitlist. Find your friends to get yourself in.")
        return

    # Authenticate user first and start doing something
    client = Clubhouse(
        user_id=user_id,
        user_token=user_token,
        user_device=user_device
    )
    if result['is_onboarding']:
        process_onboarding(client)

    return

def main():
    """
    Initialize required configurations, start with some basic stuff.
    """
    # Initialize configuration
    client = None
    user_config = read_config()
    user_id = user_config.get('user_id')
    user_token = user_config.get('user_token')
    user_device = user_config.get('user_device')

    # Check if user is authenticated
    if user_id and user_token and user_device:
        client = Clubhouse(
            user_id=user_id,
            user_token=user_token,
            user_device=user_device
        )

        # Check if user is still on the waitlist
        _check = client.check_waitlist_status()
        if _check['is_waitlisted']:
            print("[!] You're still on the waitlist. Find your friends to get yourself in.")
            return

        # Check if user has not signed up yet.
        _check = client.me()
        if not _check['user_profile'].get("username"):
            process_onboarding(client)

        chat_main(client)
    else:
        client = Clubhouse()
        user_authentication(client)
        main()

if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Remove dump files on exit.
        file_list = os.listdir(".")
        for _file in file_list:
            if _file.endswith(".dmp"):
                os.remove(_file)
