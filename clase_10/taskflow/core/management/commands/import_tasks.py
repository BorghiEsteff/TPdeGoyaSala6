import csv
import json
import logging
import os
import xml.etree.ElementTree as ET
from django.core.management.base import BaseCommand
from core.models import Task

logger = logging.getLogger("import_tasks")
log_handler = logging.FileHandler("import.log", encoding="utf-8")
log_handler.setFormatter(
    logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
)
logger.addHandler(log_handler)
logger.setLevel(logging.INFO)


class Command(BaseCommand):
    help = "Importa tareas desde múltiples proveedores (JSON, CSV, XML)"

    def handle(self, *args, **options):
        total = 0
        total += self._import_json("data/tasks_provider_a.json", source="proveedor_a")
        total += self._import_csv("data/tasks_provider_b.csv", source="proveedor_b")
        total += self._import_xml("data/tasks_provider_c.xml", source="proveedor_c")

        if os.path.exists("data/tasks_provider_d.json"):
            total += self._import_json("data/tasks_provider_d.json", source="proveedor_d")

        mensaje = f"Importación finalizada: {total} tareas cargadas"
        self.stdout.write(self.style.SUCCESS(mensaje))
        logger.info(mensaje)

    def _import_json(self, path, source):
        count = 0
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            for item in data:
                if self._crear_task(item, source):
                    count += 1
        except (FileNotFoundError, json.JSONDecodeError) as e:
            err_msg = f"Error importando {path}: {e}"
            self.stderr.write(self.style.ERROR(err_msg))
            logger.error(err_msg)
        return count

    def _import_csv(self, path, source):
        count = 0
        try:
            with open(path, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if self._crear_task(row, source):
                        count += 1
        except FileNotFoundError as e:
            err_msg = f"Error importando {path}: {e}"
            self.stderr.write(self.style.ERROR(err_msg))
            logger.error(err_msg)
        return count

    def _import_xml(self, path, source):
        count = 0
        try:
            tree = ET.parse(path)
            for task_el in tree.getroot().findall("task"):
                title_node = task_el.find("title")
                priority_node = task_el.find("priority")
                status_node = task_el.find("status")

                item = {
                    "title": title_node.text if title_node is not None else "",
                    "priority": priority_node.text if priority_node is not None else "media",
                    "status": status_node.text if status_node is not None else "pendiente",
                }
                if self._crear_task(item, source):
                    count += 1
        except (FileNotFoundError, ET.ParseError) as e:
            err_msg = f"Error importando {path}: {e}"
            self.stderr.write(self.style.ERROR(err_msg))
            logger.error(err_msg)
        return count

    def _crear_task(self, item, source):
        title = item.get("title")
        if not title:
            warn_msg = f"[{source}] Item sin título, se ignora: {item}"
            self.stderr.write(self.style.WARNING(warn_msg))
            logger.warning(warn_msg)
            return False

        Task.objects.create(
            title=title,
            priority=item.get("priority", "media"),
            status=item.get("status", "pendiente"),
            source=source,
        )
        return True
