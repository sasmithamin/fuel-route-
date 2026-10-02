import csv
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from planner.models import City, Station


class Command(BaseCommand):
    help = "Load the cleaned + geocoded stations and the city gazetteer (idempotent)."

    @transaction.atomic
    def handle(self, *args, **opts):
        data = Path(settings.BASE_DIR) / "data"

        with open(data / "stations_geocoded.csv", newline="") as f:
            stations = [Station(
                opis_id=int(r["opis_id"]), name=r["name"], address=r["address"], city=r["city"],
                state=r["state"], rack_id=int(r["rack_id"]) if r["rack_id"] else None,
                price=float(r["price"]), lat=float(r["lat"]), lng=float(r["lng"]))
                for r in csv.DictReader(f)]
        Station.objects.all().delete()
        Station.objects.bulk_create(stations, batch_size=2000)

        with open(data / "us_cities.csv", newline="") as f:
            seen, cities = set(), []
            for r in csv.DictReader(f):
                k = (r["key"], r["state"])
                if k in seen:
                    continue
                seen.add(k)
                cities.append(City(key=r["key"], name=r["name"], state=r["state"],
                                   lat=float(r["lat"]), lng=float(r["lng"])))
        City.objects.all().delete()
        City.objects.bulk_create(cities, batch_size=5000)

        self.stdout.write(self.style.SUCCESS(
            f"Loaded {len(stations)} stations and {len(cities)} cities."))