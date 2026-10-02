from django.db import models


class City(models.Model):
    """Gazetteer used to resolve 'City, ST' inputs locally (no external geocoding call)."""
    key = models.CharField(max_length=120)          # normalised name
    name = models.CharField(max_length=120)
    state = models.CharField(max_length=2)
    lat = models.FloatField()
    lng = models.FloatField()

    class Meta:
        indexes = [models.Index(fields=["key", "state"])]


class Station(models.Model):
    opis_id = models.IntegerField(unique=True)
    name = models.CharField(max_length=200)
    address = models.CharField(max_length=200)
    city = models.CharField(max_length=120)
    state = models.CharField(max_length=2)
    rack_id = models.IntegerField(null=True)
    price = models.FloatField(help_text="USD per gallon")
    lat = models.FloatField()
    lng = models.FloatField()

    def __str__(self):
        return f"{self.name} ({self.city}, {self.state}) ${self.price:.3f}"