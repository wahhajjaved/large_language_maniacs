# coding: utf-8

# Copyright (C) University of Southern California (http://usc.edu)
# Author: Vladimir M. Zaytsev <zaytsev@usc.edu>
# URL: <http://nlg.isi.edu/>
# For more information, see README.md
# For license information, see LICENSE


import simplejson as json
import pipeline.external as adb

from pipeline.models import TASK_STATUS


class Annotator(object):

    def __init__(self, logger, task):
        self.logger = logger
        self.task = task

    def task_error(self, error_msg, error_code=None, count_error=False):
        self.logger.error(error_msg)
        self.task.log_error(error_msg)
        self.task.task_error_message = error_msg
        if error_code is not None:
            self.task.task_error_code = error_code
        if count_error:
            self.task.task_error_count += 1
        return self.task

    def annotate(self):

        # 1.
        log_msg = "Start annotating document."
        self.logger.info(log_msg)
        self.task.log_error(log_msg)
        metaphors = {}
        request_document_body = self.task.request_body


        # 2. Parse document JSON
        log_msg = "Parse document json. Task id=%d, document size=%d.." % (self.task.id, len(request_document_body))
        self.logger.info(log_msg)
        self.task.log_error(log_msg)
        request_document = json.loads(request_document_body)

        last_step = request_document_body.get("step", 3)
        if last_step not in (1, 2, 3):
            log_msg = "Wrong last step value: %r" % last_step
            self.logger.info(log_msg)
            self.task.log_error(log_msg)
            last_step = 3


        # 3. Get document language.
        log_msg = "Getting document language. Task id=%d." % self.task.id
        self.logger.info(log_msg)
        self.task.log_error(log_msg)
        try:
            language = request_document["language"]
        except KeyError:
            error_msg = "No language information available. Task id=%d." % self.task.id
            return self.task_error(error_msg, 3)
        self.task.request_lang = language

        # 4. Get annotation records.
        self.logger.info("Getting document annotations. Task id=%d." % self.task.id)
        try:
            annotations = request_document["metaphorAnnotationRecords"]
        except KeyError:
            error_msg = "No annotations available. Task id=%d." % self.task.id
            return self.task_error(error_msg, 4)

        # 5. Extract annotations.
        self.logger.info("Extracting metaphor entries from document. Task id=%d." % self.task.id)
        annotation_id_index = 0

        for annotation_no, annotation in enumerate(annotations):
            self.logger.info("Extracting annotation #%d." % annotation_no)

            # 5.1 Extracting annotation ID.
            try:
                annotation_id = annotation["sentenceId"]
            except KeyError:
                error_msg = "Ann #%d. No annotation id available (sentenceId). Task=%d" % (
                    annotation_no,
                    self.task.id,
                )
                self.task_error(error_msg, error_code=None, count_error=True)
                annotation_id_index += 1
                annotation_id = annotation_id_index

            # 5.2
            try:
                metaphor = annotation["linguisticMetaphor"]
                if language == "EN":
                    # Replacing single quote, double quote (start/end), dash
                    ascii_metaphor = metaphor.replace(u"\u2019", u"\u0027")\
                                             .replace(u"\u201c", u"\u0022")\
                                             .replace(u"\u201d", u"\u0022")\
                                             .replace(u"\u2014", u"\u002d")

                    metaphors[str(annotation_id)] = ascii_metaphor.encode("utf-8")

                else:

                    metaphors[str(annotation_id)] = metaphor.encode("utf-8")

            except KeyError:
                error_msg = "Ann #%d. No metaphor available (skip it). Task=%d" % (
                    annotation_no,
                    self.task.id,
                )
                self.task_error(error_msg, error_code=None, count_error=True)

        self.logger.info("Task %d language=%s" % (self.task.id, language))
        self.task.language = language
        self.task.task_status = TASK_STATUS.PREPROCESSED
        self.task.response_status = 200

        # 6. If there are no metaphors for annotation, return error.
        if len(metaphors) == 0:
            error_msg = "Found 0 metaphors for annotation. Task id=#%d."
            return self.task_error(error_msg, 6)

        result = adb.run_annotation(request_document,
                                    metaphors,
                                    language,
                                    self.task,
                                    self.logger,
                                    with_pdf_content=True,
                                    last_step=last_step)

        self.task.response_body = result
        self.task.task_status = TASK_STATUS.PROCESSED

        return self.task


