# -*- coding: utf-8 -*-

import argparse
import collections
import dataclasses
import datetime
import enum
import json
import os
import pathlib
import shutil

import marshmallow_dataclass
from tabulate import tabulate


class BookingCategory(str, enum.Enum):
    FLEXI = "FLEXI"
    HOLIDAY = "HOLIDAY"
    MOBILE = "MOBILE"
    OFFICE = "OFFICE"
    SICK = "SICK"
    VACATION = "VACATION"


@dataclasses.dataclass
class Booking:
    checkin_timestamp: datetime.datetime | None = None
    checkout_timestamp: datetime.datetime | None = None
    pause: float = 0.5
    productive_time: float = 0
    delta: float = 0
    category: BookingCategory = BookingCategory.MOBILE
    description: str | None = None


@dataclasses.dataclass
class KeeperFile:
    bookings: dict[str, Booking]


class CheckInOutAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        if values is None:
            values = datetime.datetime.now().strftime("%H:%M")
        else:
            try:
                values = datetime.datetime.strptime(values, "%H:%M").strftime("%H:%M")
            except ValueError:
                raise argparse.ArgumentTypeError("Invalid time format; please use 24h notation 'hh:mm'")
        setattr(namespace, self.dest, values)


KeeperFileSchema = marshmallow_dataclass.class_schema(KeeperFile)


class Keeper:
    def __init__(self, args) -> None:
        """Initialize the Keeper."""
        self.__storage_directory = pathlib.Path.home() / ".keeper"
        self.__load_config()
        self.__keeper_file_path = self.__storage_directory /  "keeper.json"
        self.__contracted_working_hours = self.__config.get("contracted_working_hours", 8)
        self.__default_category = self.__config.get("default_category", BookingCategory.MOBILE)
        self.__default_pause_length = self.__config.get("default_pause_length", 0.5)
        self.__start_delta = self.__config.get("start_delta", 0)
        self.__load_data()
        self.__day_to_work_on = datetime.datetime.now().replace(tzinfo=None)
        self.__process_args(args)

    def __load_config(self) -> None:
        """Load the configuration file."""
        if not os.path.isdir(self.__storage_directory):
            os.mkdir(self.__storage_directory)
        if not os.path.isfile(self.__storage_directory / "keeper_settings.json"):
            with open(self.__storage_directory / "keeper_settings.json", "w", encoding="utf-8") as f:
                json.dump({"contracted_working_hours": 8, "default_category": "MOBILE", "default_pause_length": 0.5, "backup": True}, f, indent=4)
        with open(self.__storage_directory / "keeper_settings.json", "r", encoding="utf-8") as f:
            self.__config = json.load(f)

    def __backup_keeper_file(self) -> None:
        """Create a backup of the keeper file."""
        if os.path.isfile(self.__keeper_file_path):
            shutil.copy(self.__keeper_file_path, self.__storage_directory / "keeper.json.backup")

    def __load_data(self) -> None:
        """Load the keeper file."""
        if not os.path.isfile(self.__keeper_file_path):
            with open(self.__keeper_file_path, "w", encoding="utf-8") as f:
                json.dump({"bookings": {}}, f, indent=4)
        with open(self.__keeper_file_path, "r", encoding="utf-8") as f:
            json_str = json.load(f)
            self.__data = KeeperFileSchema().load(json_str).bookings

    def __save_data(self) -> None:
        """Save the keeper file."""
        sorted_data = collections.OrderedDict(sorted(self.__data.items()))
        with open(self.__keeper_file_path, "w", encoding="utf-8") as f:
            json.dump(KeeperFileSchema().dump(KeeperFile(bookings=sorted_data)), f, indent=4)

    def __process_args(self, args: argparse.Namespace) -> None:
        """Process the arguments. Set the day to work on and process the parameters. Backup the keeper file if data is saved."""
        parameter = False
        if args.balance or args.category or args.description or args.checkin or args.checkout or args.pause or args.remove:
            if self.__config.get("backup", True):
                self.__backup_keeper_file()
        if args.date:
            self.__day_to_work_on = datetime.datetime.fromisoformat(args.date)
        if args.description:
            parameter = True
            self.__set_description(args.description)
        if args.balance:
            parameter = True
            self.__recalculate_balance()
            self.__print_balance()
        if args.checkin:
            parameter = True
            self.__check(True, args.checkin)
        if args.checkout:
            parameter = True
            self.__check(False, args.checkout)
            self.__print_balance()
        if args.today:
            parameter = True
            self.__print_table(self.generate_day_keys(1))
        if args.category:
            parameter = True
            if args.category in BookingCategory:
                self.__category(BookingCategory(args.category))
            else:
                print(f"Unknown value: {args.category}")
        if args.list is not None:
            parameter = True
            days = args.list if args.list else 7
            self.__print_table(self.generate_day_keys(days))
            self.__print_balance()
        if args.pause is not None:
            parameter = True
            self.__set_pause(args.pause)
        if args.remove:
            parameter = True
            self.__remove_booking(args.remove)
        if not parameter:
            print("No parameter set. Please use '--help' for more information.")

    def __check(self, checkin: bool, booking_time: str) -> None:
        """Check in or out and save data."""
        booking_date = datetime.datetime.fromisoformat(f"{self.__day_to_work_on.strftime("%Y-%m-%d")} {booking_time}")
        key = self.__day_to_work_on.strftime("%Y-%m-%d")
        booking = Booking(category=BookingCategory(self.__default_category), pause=self.__default_pause_length)
        if self.__data.get(key):
            booking = self.__data[key]
        if checkin:
            booking.checkin_timestamp = booking_date
        else:
            booking.checkout_timestamp = booking_date
        if booking.checkin_timestamp and booking.checkout_timestamp:
            difference = booking.checkout_timestamp - booking.checkin_timestamp
            booking.productive_time = self.quarter_round(difference.seconds / 60 / 60) - booking.pause
            booking.delta = booking.productive_time - self.__contracted_working_hours

        self.__data[key] = booking
        self.__save_data()
        self.__print_table([key])

    def __set_description(self, description: str) -> None:
        """Set the description for the booking."""
        key = self.__day_to_work_on.strftime("%Y-%m-%d")
        booking = self.__get_or_create_booking()
        booking.description = description
        self.__store_and_print(key, booking)

    def __category(self, category: BookingCategory) -> None:
        """Set the category for the booking."""
        key = self.__day_to_work_on.strftime("%Y-%m-%d")
        booking = self.__get_or_create_booking()
        booking.category = category
        if category == BookingCategory.FLEXI:
            booking.productive_time = 0
            booking.checkin_timestamp = None
            booking.checkout_timestamp = None
            booking.pause = 0
            booking.delta = - self.__contracted_working_hours
        if category == BookingCategory.HOLIDAY or category == BookingCategory.VACATION or category == BookingCategory.SICK:
            booking.productive_time = 0
            booking.checkin_timestamp = None
            booking.checkout_timestamp = None
            booking.pause = 0
            booking.delta = 0
        self.__store_and_print(key, booking)

    def __set_pause(self, pause: float) -> None:
        """Set the pause time in hours for the booking."""
        key = self.__day_to_work_on.strftime("%Y-%m-%d")
        booking = self.__get_or_create_booking()
        booking.pause = pause
        if booking.checkin_timestamp and booking.checkout_timestamp:
            difference = booking.checkout_timestamp - booking.checkin_timestamp
            booking.productive_time = self.quarter_round(difference.seconds / 60 / 60) - booking.pause
            booking.delta = booking.productive_time - self.__contracted_working_hours
        self.__store_and_print(key, booking)

    def __remove_booking(self, date: str) -> None:
        """Remove the booking for the given date."""
        key = datetime.datetime.fromisoformat(date).strftime("%Y-%m-%d")
        if key in self.__data:
            del self.__data[key]
            self.__save_data()
            print(f"Booking on {date} has been removed.")
        else:
            print(f"No booking found on {date}.")

    def __print_table(self, keys: list[str]) -> None:
        """Print the table for the given keys."""
        table = [
            ["DAY", "DATE", "IN", "OUT", "PROD TIME", "DELTA", "PAUSE", "CATEGORY", "DESCRIPTION"]
        ]
        for key in keys:
            if key in self.__data and self.__data[key].checkin_timestamp:
                day = self.__data[key]
                productive_time_value: float
                if day.productive_time:
                    productive_time_value = day.productive_time
                else:
                    difference = datetime.datetime.now() - day.checkin_timestamp
                    productive_time_value = (self.quarter_round(difference.seconds / 60 / 60) - day.pause)
                table.append(
                    [day.checkin_timestamp.strftime("%a"), key, day.checkin_timestamp.strftime("%H:%M"), day.checkout_timestamp.strftime("%H:%M") if day.checkout_timestamp else "", productive_time_value, day.delta ,day.pause, day.category.value, day.description])
            elif key in self.__data and self.__data[key].category:
                day = self.__data[key]
                table.append([datetime.datetime.fromisoformat(key).strftime("%a"), key, "---", "---", day.productive_time, day.delta, "---", day.category.value, "---" if not day.description else day.description])
            else:
                if datetime.datetime.fromisoformat(key).strftime("%a") == "Sat" or datetime.datetime.fromisoformat(key).strftime("%a") == "Sun":
                    table.append([datetime.datetime.fromisoformat(key).strftime("%a"), key, "///", "///", "///", "///", "///", "WEEKEND", "///"])
                else:
                    table.append([datetime.datetime.fromisoformat(key).strftime("%a"), key, "---", "---", "---", "---", "---", "---", "---"])

        print(tabulate(table, tablefmt='fancy_grid'))

    def __get_or_create_booking(self) -> Booking:
        """Get the booking for the given date or create a new one."""
        key = self.__day_to_work_on.strftime("%Y-%m-%d")
        if key in self.__data:
            return self.__data[key]
        return Booking(category=self.__default_category, pause=self.__default_pause_length)

    def __recalculate_balance(self) -> None:
        """Recalculate the time balance for single days."""
        for key in self.__data:
            day: Booking = self.__data[key]
            if day.checkin_timestamp and day.checkout_timestamp:
                difference = day.checkout_timestamp - day.checkin_timestamp
                day.productive_time = self.quarter_round(difference.seconds / 60 / 60) - day.pause
                day.delta = day.productive_time - self.__contracted_working_hours
                self.__store_and_print(key, day)
            elif day.category == BookingCategory.FLEXI:
                day.productive_time = 0
                day.checkin_timestamp = None
                day.checkout_timestamp = None
                day.pause = 0
                day.delta = - self.__contracted_working_hours
                self.__store_and_print(key, day)

    def __print_balance(self) -> None:
        """Print the overall time balance."""
        balance = 0 + self.__start_delta
        for key in self.__data:
            balance += self.__data[key].delta
        print(f"Overall time balance: {balance} hours")

    def __store_and_print(self, key: str, booking: Booking) -> None:
        """Store the booking and print the table."""
        self.__data[key] = booking
        self.__save_data()
        self.__print_table([key])

    @staticmethod
    def generate_day_keys(days: int) -> list[str]:
        """Generate the keys for the given number of days."""
        key_list: list[str] = []
        for day in range(days):
            d = datetime.datetime.today() - datetime.timedelta(days=day)
            key_list.append(d.strftime("%Y-%m-%d"))
        return key_list[::-1]

    @staticmethod
    def quarter_round(x: float, base: float = 0.25):
        """Round to the nearest quarter."""
        return base * round(x / base)


def main() -> None:
    """Main function."""
    parser = argparse.ArgumentParser(description="Keep track of your working hours")
    parser.add_argument("-b", "--balance", action="store_true", help="Recalculate and print overall time balance")
    parser.add_argument("-c", "--category", type=str, help=f"Categorize day; possible values: {", ".join([c.value for c in BookingCategory])}")
    parser.add_argument("-d", "--date", type=str, help="Give a date to book on; format dd.mm.yyyy")
    parser.add_argument("-dsc", "--description", type=str, help="Add a description for the booking")
    parser.add_argument("-i", "--checkin", nargs='?', action=CheckInOutAction, help="Check in now or at given time; format: hh:mm")
    parser.add_argument("-l", "--list", nargs='?', const=7, type=int, help="List bookings for the given number of days (default: 7 days)")
    parser.add_argument("-o", "--checkout", nargs='?', action=CheckInOutAction, help="Check out now or at given time; format: hh:mm")
    parser.add_argument("-p", "--pause", type=float, help="Set pause time in hours")
    parser.add_argument("-rm", "--remove", type=str, help="Remove booking on given date")
    parser.add_argument("-t", "--today", action="store_true", help="Print current day")

    Keeper(parser.parse_args())

if __name__ == "__main__":
    main()
