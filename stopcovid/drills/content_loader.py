import json
import logging
import os
from copy import copy
from typing import Dict, List
from abc import ABC, abstractmethod
from collections import defaultdict

import boto3

from .drills import Drill, DrillSchema

__location__ = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))


class ContentLoader(ABC):
    def __init__(self):
        self.drills_dict = {}
        self.all_drill_slugs = []
        self.translations_dict = defaultdict(dict)
        self._populate_content()

    @abstractmethod
    def _populate_content(self):
        pass

    @abstractmethod
    def _is_content_stale(self) -> bool:
        pass

    def _populate_drills(self, drill_content: str):
        self.drills_dict = {}
        self.all_drill_slugs = []
        raw_drills = json.loads(drill_content)
        for drill_slug, raw_drill in raw_drills.items():
            self.drills_dict[drill_slug] = DrillSchema().load(raw_drill)
            self.all_drill_slugs.append(drill_slug)

        # dictionaries are unordered, so we determine drill order by sorting the drill slugs
        self.all_drill_slugs.sort()

    def _populate_translations(self, translations_content: str):
        self.translations_dict = defaultdict(dict)
        raw_translations = json.loads(translations_content)
        for entry in raw_translations["instructions"]:
            self.translations_dict[entry["language"]][entry["label"]] = entry["translation"]

    def get_drills(self) -> Dict[str, Drill]:
        if self._is_content_stale():
            self._populate_content()
        return self.drills_dict

    def get_translations(self) -> Dict[str, Dict[str, str]]:
        if self._is_content_stale():
            self._populate_content()
        return self.translations_dict

    def get_all_drill_slugs(self) -> List[str]:
        if self._is_content_stale():
            self._populate_content()
        return copy(self.all_drill_slugs)


class SourceRepoLoader(ContentLoader):
    def _populate_content(self):
        logging.info("Loading drill content from the file system")
        with open(os.path.join(__location__, "drill_content/drills.json")) as f:
            self._populate_drills(f.read())
        with open(os.path.join(__location__, "drill_content/translations.json")) as f:
            self._populate_translations(f.read())

    def _is_content_stale(self) -> bool:
        return False


class S3Loader(ContentLoader):
    def __init__(self, s3_bucket):
        self.s3_bucket = s3_bucket
        self.s3 = boto3.resource("s3")
        super().__init__()

    def _populate_content(self):
        logging.info(f"Loading drill content from the {self.s3_bucket} S3 bucket")
        drill_object = self.s3.Object(self.s3_bucket, "drills.json")
        translations_object = self.s3.Object(self.s3_bucket, "translations.json")
        self.drill_version = drill_object.version_id
        self.translations_version = translations_object.version_id

        self._populate_drills(drill_object.get()["Body"].read().decode("utf-8"))
        self._populate_translations(translations_object.get()["Body"].read().decode("utf-8"))

    def _is_content_stale(self) -> bool:
        try:
            drill_object = self.s3.Object(self.s3_bucket, "drills.json")
            translations_object = self.s3.Object(self.s3_bucket, "translations.json")
            if (
                self.drill_version != drill_object.version_id
                or self.translations_version != translations_object.version_id
            ):
                logging.info("Drill or translation objects have changed in S3.")
                return True
            return False
        except Exception:
            logging.warning(
                "S3 loader error checking drill or translation version. Assuming that "
                "content is not stale.",
                exc_info=True,
            )
            return False


CONTENT_LOADER = None


def get_content_loader() -> ContentLoader:
    global CONTENT_LOADER
    if CONTENT_LOADER is None:
        s3_bucket = os.getenv("DRILL_CONTENT_S3_BUCKET")
        if s3_bucket:
            CONTENT_LOADER = S3Loader(s3_bucket)
        else:
            CONTENT_LOADER = SourceRepoLoader()
    return CONTENT_LOADER
