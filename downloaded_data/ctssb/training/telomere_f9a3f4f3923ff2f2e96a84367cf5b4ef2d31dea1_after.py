import datetime
from flask import flash, redirect, url_for, request, render_template, send_from_directory
from flask.ext.login import login_required
from app import db, telomere
from app.forms.spreadsheet import SpreadsheetUpload
from app.services.spreadsheet import SpreadsheetService
from app.services.batch import BatchService
from app.services.sample import SampleService
from app.model.spreadsheet import Spreadsheet
from flask_login import current_user

@login_required
@telomere.route('/spreadsheet/upload/', methods=['GET', 'POST'])
def speadsheet_upload():

    form = SpreadsheetUpload()

    if form.validate_on_submit():
        batchService = BatchService()
        batch = batchService.SaveAndReturn(form.batch)

        if (batch):
            spreadsheetService = SpreadsheetService()
            spreadsheet = spreadsheetService.SaveAndReturn(form.spreadsheet.data, batch)
            errors = spreadsheetService.Process(spreadsheet)

            if len(errors) > 0:
                for e in errors:
                    flash(e)

                db.session.rollback()
            else:
                flash("File '%s' Uploaded" % spreadsheet.filename)

                db.session.commit()

                return redirect(url_for('batch_index'))

    return render_template('spreadsheet/upload.html', form=form)

@telomere.route("/spreadsheet/process/<int:id>", methods=['POST'])
@login_required
def speadsheet_process(id):
    spreadsheetService = SpreadsheetService()
    spreadsheet = Spreadsheet.query.get(id)
    errors = spreadsheetService.Process(spreadsheet)

    for e in errors:
        flash(e)

    db.session.commit()

    return redirect(url_for('batch_index'))

@telomere.route("/spreadsheet/download/<int:id>")
@login_required
def speadsheet_download(id):
    spreadsheet = Spreadsheet.query.get(id)
    service = SpreadsheetService()

    return send_from_directory(telomere.config['SPREADSHEET_UPLOAD_DIRECTORY'], service.GetFilename(spreadsheet), as_attachment=True, attachment_filename=spreadsheet.filename)


