import time

from django.core.management.base import BaseCommand
from django.utils import timezone
import asyncio


from netbox_proxbox.proxbox_api_v2.scrapper import Scrapper


class Command(BaseCommand):
    help = "Run the proxbox scrapper"

    def add_arguments(self, parser):
        # parser.add_argument('reports', nargs='+', help="Report(s) to run")
        pass

    def handle(self, *args, **options):
        asyncio.run(Scrapper.async_run())
        # Scrapper.run()
        # Wrap things up
        self.stdout.write(
            "[{:%H:%M:%S}] Finished".format(timezone.now())
        )
