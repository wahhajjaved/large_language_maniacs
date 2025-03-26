# Copyright (C) 2017 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

"""
add_issutracker_issue

Create Date: 2017-10-20 21:23:14.623483
"""
# disable Invalid constant name pylint warning for mandatory Alembic variables.
# pylint: disable=invalid-name

import sqlalchemy as sa

from alembic import op


# revision identifiers, used by Alembic.
revision = 'ee816a4379e'
down_revision = '2ad7783c176'


def upgrade():
  """Upgrade database schema and/or data, creating a new revision."""
  op.create_table(
      'issuetracker_issues',

      sa.Column('object_id', sa.Integer(), nullable=False),
      sa.Column('object_type', sa.String(250), nullable=False),
      sa.Column('enabled', sa.Boolean, nullable=False, default=False),
      sa.Column('title', sa.String(250), nullable=False),
      sa.Column('component_id', sa.String(50), nullable=False),
      sa.Column('hotlist_id', sa.String(50), nullable=True),
      sa.Column('issue_type', sa.String(50), nullable=False),
      sa.Column('issue_priority', sa.String(50), nullable=False),
      sa.Column('issue_severity', sa.String(50), nullable=False),
      sa.Column('assignee', sa.String(250), nullable=True),
      sa.Column('cc_list', sa.Text, nullable=True),

      sa.Column('issue_id', sa.String(50), nullable=True),
      sa.Column('issue_url', sa.String(250), nullable=True),

      sa.Column('modified_by_id', sa.Integer()),
      sa.Column('context_id', sa.Integer(), sa.ForeignKey('contexts.id')),
      sa.Column('created_at', sa.DateTime()),
      sa.Column('updated_at', sa.DateTime()),

      sa.UniqueConstraint(
          'object_type', 'object_id', name='uq_object_id_object_type'),
  )

def downgrade():
  """Downgrade database schema and/or data back to the previous revision."""
  op.drop_table('issuetracker_issues')
