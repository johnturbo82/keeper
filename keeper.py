# -*- coding: utf-8 -*-

import argparse
import dataclasses
import enum
import json
import datetime
import os

import marshmallow_dataclass
from tabulate import tabulate


class BookingCategory(str, enum.Enum):
    VACATION = "VACATION"
    SICK = "SICK"
    HOLIDAY = "HOLIDAY"
    MOBILE = "MOBILE"
    OFFICE = "OFFICE"


@dataclasses.dataclass
class Booking:
    checkin_timestamp: datetime.datetime | None = None
    checkout_timestamp: datetime.datetime | None = None
    pause: float = 0.5
    productive_time: float = 0
    category: BookingCategory = BookingCategory.MOBILE
    description: str | None = None


@dataclasses.dataclass
class KeeperFile:
    bookings: dict[str, Booking]


KeeperFileSchema = marshmallow_dataclass.class_schema(KeeperFile)


class Keeper:
    def __init__(self, args) -> None:
        self.__load_config()
        self.__keeper_file_path = self.__config.get("keeper_file", "keeper.json")
        self.__contracted_working_hours = self.__config.get("contracted_working_hours", 8)
        self.__default_pause_length = self.__config.get("default_pause_length", 0.5)
        self.__load_data()
        self.__day_to_work_on = datetime.datetime.now().replace(tzinfo=None)
        self.__process_args(args)

    def __load_config(self) -> None:
        if not os.path.isfile("keeper_settings.json"):
            with open("keeper_settings.json", "w", encoding="utf-8") as f:
                json.dump({ "keeper_file": "keeper.json", "contracted_working_hours": 8, "default_pause_length": 0.5 }, f, indent=4)
        with open("keeper_settings.json", "r", encoding="utf-8") as f:
            self.__config = json.load(f)

    def __load_data(self) -> None:
        if not os.path.isfile(self.__keeper_file_path):
            with open(self.__keeper_file_path, "w", encoding="utf-8") as f:
                json.dump({ "bookings": {} }, f, indent=4)
        with open(self.__keeper_file_path, "r", encoding="utf-8") as f:
            json_str = json.load(f)
            self.__data = KeeperFileSchema().load(json_str).bookings

    def __save_data(self) -> None:
        with open(self.__keeper_file_path, "w", encoding="utf-8") as f:
            json.dump(KeeperFileSchema().dump(KeeperFile(bookings=self.__data)), f, indent=4)

    def __process_args(self, args: argparse.Namespace) -> None:
        parameter = False
        if args.date:
            self.__day_to_work_on = datetime.datetime.fromisoformat(args.date)
        if args.checkin:
            parameter = True
            self.__check(True)
        if args.checkin_at:
            parameter = True
            self.__check(True, args.checkin_at)
        if args.checkout:
            parameter = True
            self.__check(False)
        if args.checkout_at:
            parameter = True
            self.__check(False, args.checkout_at)
        if args.today:
            parameter = True
            self.print_table(self.generate_day_keys(1))
        if args.week:
            parameter = True
            self.print_table(self.generate_day_keys(7))
        if args.month:
            parameter = True
            self.print_table(self.generate_day_keys(30))
        if args.category:
            parameter = True
            if args.category not in BookingCategory:
                print(f"Unknown value: {args.category}")
            else:
                print(args.category) # TODO
        if not parameter:
            print("No parameter set. Please use '--help' for more information.")


    def __check(self, checkin: bool, booking_time: str = None) -> None:
        if booking_time:
            booking_date = datetime.datetime.fromisoformat(f"{self.__day_to_work_on.strftime("%Y-%m-%d")} {booking_time}")
        else:
            booking_date = self.__day_to_work_on
        key = self.__day_to_work_on.strftime("%Y-%m-%d")
        booking = Booking()
        if self.__data.get(key):
            booking = self.__data[key]
        if checkin:
            booking.checkin_timestamp = booking_date
        else:
            booking.checkout_timestamp = booking_date
        if booking.checkin_timestamp and booking.checkout_timestamp:
            difference = booking.checkout_timestamp - booking.checkin_timestamp
            booking.productive_time = self.quarter_round(difference.seconds / 60 / 60) - self.__default_pause_length

        self.__data[key] = booking
        self.__save_data()
        self.print_table([key])

    def print_table(self, keys: list[str]) -> None:
        table = [
            ["DAY", "DATE", "IN", "OUT", "PROD TIME", "PAUSE", "CATEGORY", "DESCRIPTION"]
        ]
        for key in keys:
            if key in self.__data:
                day = self.__data[key]
                productive_time_value: float
                if day.productive_time:
                    productive_time_value = day.productive_time
                else:
                    difference = datetime.datetime.now() - day.checkin_timestamp
                    productive_time_value = (self.quarter_round(difference.seconds / 60 / 60) - day.pause)
                table.append([day.checkin_timestamp.strftime("%a"), key, day.checkin_timestamp.strftime("%H:%M"), day.checkout_timestamp.strftime("%H:%M") if day.checkout_timestamp else "", productive_time_value, day.pause, day.category.value, day.description])
            else:
                table.append([datetime.datetime.fromisoformat(key).strftime("%a"), key, "---", "---", "---", "---", "---", "---"])

        print(tabulate(table, tablefmt='fancy_grid'))

    @staticmethod
    def generate_day_keys(days: int) -> list[str]:
        key_list: list[str] = []
        for day in range(days):
            d = datetime.datetime.today() - datetime.timedelta(days=day)
            key_list.append(d.strftime("%Y-%m-%d"))
        return key_list

    @staticmethod
    def quarter_round(x: float, base: float = 0.25):
        return base * round(x / base)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process some integers.")
    parser.add_argument("-c", "--category", type=str, help=f"Categorize day; possible values: {", ".join([c.value for c in BookingCategory])}")
    parser.add_argument("-d", "--date", type=str, help="Give a date to book on; format dd.mm.yyyy")
    parser.add_argument("-i", "--checkin", default=False, help="Check in now", action="store_true")
    parser.add_argument("-ia", "--checkin_at", type=str, help="Check in at given time; format: hh:mm")
    parser.add_argument("-o", "--checkout", default=False, help="Check out now", action="store_true")
    parser.add_argument("-oa", "--checkout_at", type=str, help="Check out at given time; format: hh:mm")
    parser.add_argument("-t", "--today", action="store_true" ,help="Print current day")
    parser.add_argument("-w", "--week", default=False, action="store_true" ,help="Print current week")
    parser.add_argument("-m", "--month", default=False, action="store_true" ,help="Print current month")

    keeper = Keeper(parser.parse_args())
