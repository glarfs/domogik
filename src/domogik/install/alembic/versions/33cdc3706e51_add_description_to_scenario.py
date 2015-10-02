"""Add description to scenario

Revision ID: 33cdc3706e51
Revises: 50c473f3e798
Create Date: 2015-07-16 20:01:32.882152

"""

# revision identifiers, used by Alembic.
revision = '33cdc3706e51'
down_revision = '50c473f3e798'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column(u'core_scenario', sa.Column('description', sa.Text(), nullable=True))
    ### end Alembic commands ###


def downgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.drop_column(u'core_scenario', 'description')
    ### end Alembic commands ###