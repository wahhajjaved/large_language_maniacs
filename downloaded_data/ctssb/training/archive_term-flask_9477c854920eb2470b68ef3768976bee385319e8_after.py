# -*- coding: utf-8 -*-
"""
    Модель реализующая принадлежность терминалов к фирмам и мультиаренду

    :copyright: (c) 2013 by Pavel Lyashkov.
    :license: BSD, see LICENSE for more details.
"""
from web import db, app, cache
from helpers import date_helper


class FirmTerm(db.Model):

    __bind_key__ = 'term'
    __tablename__ = 'firm_term'

    id = db.Column(db.Integer, primary_key=True)
    term_id = db.Column(db.Integer, db.ForeignKey('term.id'), index=True)
    term = db.relationship('Term')
    firm_id = db.Column(db.Integer, db.ForeignKey('firm.id'), index=True)
    firm = db.relationship(
        'Firm',
        primaryjoin="Firm.id==FirmTerm.firm_id")
    child_firm_id = db.Column(db.Integer, db.ForeignKey('firm.id'))
    child_firm = db.relationship(
        'Firm',
        primaryjoin="Firm.id==FirmTerm.child_firm_id")

    creation_date = db.Column(db.DateTime, nullable=False)

    def __init__(self):
        self.creation_date = date_helper.get_curent_date()

    def __repr__(self):
        return '<id %r>' % (self.id)

    def get_list_by_term_id(self, term_id):
        firm_terms = self.query.filter_by(
            term_id=term_id).all()

        firm_id_list = []
        for firm_term in firm_terms:
            firm_id_list.append(firm_term.child_firm_id)

        return firm_id_list

    @cache.cached(timeout=30, key_prefix='list_by_firm_id')
    def get_list_by_firm_id(self, firm_id, child=True):
        query = self.query

        if child:
            query = query.filter_by(child_firm_id=firm_id)
        else:
            query = query.filter_by(firm_id=firm_id)

        firm_terms = query.all()

        firm_id_list = []
        for firm_term in firm_terms:
            firm_id_list.append(firm_term.term_id)

        return firm_id_list

    def get_access_by_firm_id(self, firm_id, term_id):
        result = False
        access = self.query.filter_by(
            firm_id=firm_id).filter_by(
                term_id=term_id).first()

        if access:
            result = True

        return result

    def delete(self):
        db.session.delete(self)
        db.session.commit()

    def update(self):
        db.session.commit()

    def save(self):
        try:
            db.session.add(self)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            app.logger.error(e)
            return False
        else:
            return True
