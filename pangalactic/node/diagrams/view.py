"""
A diagram scene and view
"""
import random

from PyQt5.QtGui     import QFont
from PyQt5.QtWidgets import (QGraphicsLineItem, QGraphicsScene, QGraphicsView,
                             QMessageBox, QSizePolicy)
from PyQt5.QtCore    import Qt, QLineF, QPoint, QPointF, QRectF

from louie import dispatcher

# pangalactic
from pangalactic.core                 import diagramz, state
from pangalactic.core.access          import get_perms
from pangalactic.core.utils.datetimes import dtstamp
from pangalactic.core.uberorb         import orb
from pangalactic.node.diagrams.shapes import (ObjectBlock, PortBlock,
                                              RoutedConnector, SubjectBlock)


class DiagramScene(QGraphicsScene):
    """
    The scene of a diagram

    Attributes:
        subject (ManagedObject):  Project or Product that is the subject of the
            IBD, of which the "blocks" are systems (of a Project) or components
            (of a Product)
        blocks (dict): mapping of "usage" (Acu or ProjectSystemUsage) oids to
            ObjectBlock instances for an "IBD" (internal block diagram).
    """
    default_item_color = Qt.white
    default_text_color = Qt.black
    default_line_color = Qt.black
    default_font = QFont()

    def __init__(self, subject, parent=None):
        """
        Initialize.

        Args:
            subject (ManagedObject):  object that is the subject of the diagram
        """
        super().__init__(parent)
        w = 1600
        h = 2400
        self.setSceneRect(QRectF(0, 0, w, h))
        self.subject = subject
        self.line = None
        self.prev_point = QPoint()
        self.refresh_required = False
        self.positions = {}

    @property
    def blocks(self):
        """
        Return a mapping of "usage" (Acu or ProjectSystemUsage) oids to
        ObjectBlock instances for the diagram.
        """
        block_dict = {}
        for shape in self.items():
            if isinstance(shape, ObjectBlock):
                block_dict[shape.usage.oid] = shape
        return block_dict

    ##########################################################################
    #  Reimplementations of QGraphicsScene API methods
    ##########################################################################

    def mimeTypes(self):
        return ["application/x-pgef-hardware-product",
                "application/x-pgef-port-type",
                "application/x-pgef-port-template"]

    def dragEnterEvent(self, event):
        if (event.mimeData().hasFormat(
                                "application/x-pgef-hardware-product")
            or event.mimeData().hasFormat(
                                "application/x-pgef-port-type")
            or event.mimeData().hasFormat(
                                "application/x-pgef-port-template")):
            event.accept()
        else:
            event.ignore()

    def mousePressEvent(self, mouseEvent):
        if (mouseEvent.button() != Qt.LeftButton):
            return
        down_items = self.items(mouseEvent.scenePos())
        connectable_items = [i for i in down_items
                             if hasattr(i, 'add_connector')]
        if connectable_items:
            self.line = QGraphicsLineItem(QLineF(mouseEvent.scenePos(),
                                                 mouseEvent.scenePos()))
            self.addItem(self.line)
        else:
            # if item does NOT have 'add_connector' method, re-issue the event
            super().mousePressEvent(mouseEvent)

    def mouseMoveEvent(self, mouseEvent):
        if self.line:
            newLine = QLineF(self.line.line().p1(), mouseEvent.scenePos())
            self.line.setLine(newLine)
            self.update()
        else:
            super().mouseMoveEvent(mouseEvent)
            # AHA!!!!!  doing self.update() forces the refresh!! :D
            self.update()

    def mouseReleaseEvent(self, mouseEvent):
        if self.line:
            # first check in user has perms to modify subject
            if not 'modify' in get_perms(self.subject):
                self.removeItem(self.line)
                self.line = None
                txt = "User's roles do not permit this operation"
                notice = QMessageBox()
                notice.setText(txt)
                notice.exec_()
            else:
                # orb.log.debug(' - mouseReleaseEvent ...')
                down_items = self.items(self.line.line().p1())
                start_items = [i for i in down_items
                               if isinstance(i, PortBlock)]
                # if start_items:
                    # orb.log.debug('   start_items: %s'.format(
                                        # start_items[0].obj.id))
                up_items = self.items(self.line.line().p2())
                end_items = [i for i in up_items if isinstance(i, PortBlock)]
                # if end_items:
                    # orb.log.debug('   end_items: %s' % end_items[0].obj.id)
                self.removeItem(self.line)
                self.line = None
                if (len(start_items) and len(end_items)
                    and start_items[0] != end_items[0]):
                    start_item = start_items[0]
                    end_item = end_items[0]
                    # orb.log.debug("  - start port type: {}".format(
                                            # start_item.port.type_of_port.id))
                    # orb.log.debug("  - end port type: {}".format(
                                            # end_item.port.type_of_port.id))
                    if (start_item.port.type_of_port.id !=
                        end_item.port.type_of_port.id):
                        txt = 'Cannot connect ports of different types.'
                        notice = QMessageBox()
                        notice.setText(txt)
                        notice.exec_()
                        return
                    # orb.log.debug('   drawing RoutedConnector ...')
                    # orb.log.debug('   * start item:')
                    # orb.log.debug('     - object id: {}'.format(
                                    # start_item.obj.id))
                    # orb.log.debug('     - port id: {}'.format(
                                    # start_item.port.id))
                    # side = 'right'
                    # if start_item.right_port:
                        # side = 'left'
                    # orb.log.debug('     ({} side)'.format(side))
                    # orb.log.debug('   * end item:')
                    # orb.log.debug('     - object id: {}'.format(
                                    # end_item.obj.id))
                    # orb.log.debug('     - port id: {}'.format(
                                    # end_item.port.id))
                    # orb.log.debug('   * context id:  {}'.format(
                                    # self.subject.id))
                    # side = 'right'
                    # if end_item.right_port:
                        # side = 'left'
                    # orb.log.debug('     ({} side)'.format(side))
                    # TODO:  color will be determined by type of Port(s)
                    routing_channel = self.get_routing_channel()
                    connector = RoutedConnector(start_item, end_item,
                                                routing_channel,
                                                context=self.subject,
                                                pen_width=3)
                    start_item.add_connector(connector)
                    end_item.add_connector(connector)
                    connector.setZValue(-1000.0)
                    self.addItem(connector)
                    connector.updatePosition()
                    dispatcher.send('diagram connector added',
                                    start_item=start_item, end_item=end_item)
                    self.update()
            self.line = None
            super().mouseReleaseEvent(mouseEvent)
        else:
            # this action is not to connect ports, it is just a regular "move"
            # of a block
            # *** NOTE NOTE NOTE !!! ***
            # THE SUPERCLASS'S mouseReleaseEvent MUST BE CALLED **HERE**,
            # (*BEFORE* OTHER ACTIONS) OR ELSE THE NEXT MOVE EVENT WILL
            # MALFUNCTION (ITEM WILL JUMP TO UPPER LEFT CORNER OF SCENE)
            # ... actually probably not important now, since the 'refresh
            # diagram' signal blows the whole diagram away and starts over!
            super().mouseReleaseEvent(mouseEvent)
            ordering = self.get_block_ordering()
            if self.positions != self.get_block_positions():
                diagramz[self.subject.oid] = ordering
                dispatcher.send('refresh diagram')

    ##########################################################################
    #  End of QGraphicsScene API methods
    ##########################################################################

    def new_position(self):
        coord = random.randint(36, 144)
        point = QPoint(coord, coord)
        return self.parent().mapToScene(point)

    def get_block_positions(self):
        """
        Return the current positions of the blocks in the diagram in the form
        of a dict that maps oids of usages for blocks to their positions.
        NOTE:  this is used to set self.positions, which is used in
        mouseReleaseEvent() to determine whether any block has been moved
        (i.e., whether diagram needs to be regenerated).

        Return:  dict mapping oids to positions
        """
        # orb.log.debug('* get_block_positions')
        return {b.usage.oid: (b.x(), b.y()) for b in self.blocks.values()}

    def get_block_ordering(self):
        """
        Return the current ordering of the blocks in the diagram in the form of
        a list containing two lists: [0] oids of usages for blocks on the left
        side of the diagram from top to bottom, [1] same for blocks on the
        right side.

        Return:  list of oids
        """
        # orb.log.debug('* get_block_ordering')
        if not self.blocks:
            return []
        w = 100
        x_left = w
        x_right = 7*w
        x_middle = (x_left + x_right) / 2.0
        left_blocks = []
        right_blocks = []
        for block in self.blocks.values():
            if block.x() > x_middle:
                right_blocks.append(block)
            else:
                left_blocks.append(block)
        left_blocks.sort(key=lambda x: x.y())
        right_blocks.sort(key=lambda x: x.y())
        left_oids = [b.usage.oid for b in left_blocks]
        right_oids = [b.usage.oid for b in right_blocks]
        return left_oids, right_oids

    def create_block(self, block_type, usage=None, obj=None, pos=None,
                     width=None, height=None, right_ports=False):
        """
        Create a new block (SubjectBlock or ObjectBlock).

        Args:
            block_type (class): SubjectBlock or ObjectBlock

        Keyword Args:
            usage (Acu or ProjectSystemUsage):  the relationship between the
                created block's 'obj' and its SubjectBlock's 'obj'.
            obj (Project or Product):  the object whose usage is represented by
                the created block (only needed if block_type is SubjectBlock)
            pos (QPointF):  position of the block in parent coordinates (or
                scene coordinates if it has no parent)
            width (int):  width of the block in pixels
            height (int):  height of the block in pixels
            right_ports (bool):  flag; if True, any ports the block has will be
                on its right side, else they will be on the left side
        """
        if not pos:
            # NOTE:  for now, new_position() selects a random position ...
            pos = self.new_position()
        if not block_type or block_type is ObjectBlock:
            block = ObjectBlock(pos, scene=self, usage=usage,
                                right_ports=right_ports)
            # self.inserted_block.emit(block)
        elif block_type is SubjectBlock:
            w = width or 100
            h = height or 50
            # ports, if any, are on the right by default for SubjectBlock
            block = SubjectBlock(pos, scene=self, obj=obj, width=w, height=h)
        self.clearSelection()
        return block

    def item_doubleclick(self, item):
        """
        Drill down to next level block diagram
        """
        # NOTE:  drill-down only applies to a populated ObjectBlock (not a TBD
        # ObjectBlock), and not to SubjectBlock (a subclass)
        # orb.log.debug('* DiagramScene: item_doubleclick()')
        # orb.log.debug('  item: {}'.format(str(item)))
        # if platform.platform().startswith('Darwin'):
            # NOTE:  currently, Mac seems to be fine with drill-down! :)
            # drill-down currently crashes on OSX
            # orb.log.info('  - Mac not like drill-down -- ignoring!')
            # return
        if isinstance(item, ObjectBlock):
            if item.obj.oid != 'pgefobjects:TBD':
                if state.get('mode') == 'system':
                    if isinstance(item.usage, orb.classes['Acu']):
                        state['system'] = item.usage.component.oid
                    elif isinstance(item.usage,
                                    orb.classes['ProjectSystemUsage']):
                        state['system'] = item.usage.system.oid
                elif state.get('mode') == 'component':
                    if isinstance(item.usage, orb.classes['Acu']):
                        state['product'] = item.usage.component.oid
                    elif isinstance(item.usage,
                                    orb.classes['ProjectSystemUsage']):
                        state['product'] = item.usage.system.oid
                dispatcher.send('diagram object drill down', usage=item.usage)

    def get_routing_channel(self):
        """
        Return the left and right x-coordinates within which the vertical
        segments of connectors are to be drawn.
        """
        # orb.log.debug('* DiagramScene: get_routing_channel()')
        # find all the object blocks and group them by left and right
        if not self.blocks:
            return 300, 400
        left_xs = []
        right_xs = []
        for block in self.blocks.values():
            rp = getattr(block, 'right_ports', False)
            if rp:
                left_xs.append(block.x() + block.rect.width())
            else:
                right_xs.append(block.x())
        left_x = max(left_xs or [300])
        right_x = min(right_xs or [400])
        return left_x, right_x

    def create_ibd_subject_block(self, items):
        """
        Create the SubjectBlock for an Internal Block Diagram (IBD).

        Args:
            items (list of ObjectBlock): blocks to be enclosed
        """
        # orb.log.debug('* DiagramScene: create_ibd_subject_block()')
        if items:
            item_group = self.createItemGroup(items)
            # orb.log.debug('  - DiagramScene: created item group ...')
            brect = item_group.boundingRect()
            sb_width = brect.width() + 150
            sb_height = brect.height() + 150
            # NOTE: it is ESSENTIAL to destroy the group; otherwise the object
            # blocks in it will not receive their mouse events!
            self.destroyItemGroup(item_group)
        else:
            # if empty, give it minimum w, h
            sb_width = 300
            sb_height = 300
        return self.create_block(SubjectBlock, obj=self.subject,
                                 pos=QPointF(20, 20),
                                 width=sb_width, height=sb_height)

    def generate_ibd(self, usages, ordering=None):
        """
        Create an Internal Block Diagram (IBD) for a list of usages (Acu or
        ProjectSystemUsage instances).  If an ordering is specified, use the
        ordering.

        Args:
            usages (list of (Acu or ProjectSystemUsage): usages to create
                blocks for

        Keyword Args:
            ordering (list):  a list containing 2 lists: [0] oids of usages of
                blocks in order of appearance in the left column, [1] same for
                the right column (this ordering is returned by
                get_block_ordering()).
        """
        # orb.log.debug('* DiagramScene: generate_ibd()')
        w = 100
        h = 150
        i = 1.0
        x_left = w
        x_right = 7*w
        y_left_next = y_right_next = h
        spacing = 20
        items = []
        all_ports = []
        port_blocks = {}   # maps Port oids to PortBlock instances
        # remove current items before generating ...
        if self.items():
            for shape in self.items():
                self.removeItem(shape)
        ordering = ordering or self.get_block_ordering()
        if not len(ordering) == 2:
            # if ordering is read from a 'diagramz' cached that was in an
            # old or improper format, it will fail -- in which case, just
            # use the output of 'get_block_ordering()' instead ...
            ordering = self.get_block_ordering()
        if ordering:
            left_oids, right_oids = ordering
            # exclude any oids that don't appear in the provided 'usages'
            usage_dict = {u.oid : u for u in usages}
            left_good_oids = [oid for oid in left_oids if oid in usage_dict]
            right_good_oids = [oid for oid in right_oids if oid in usage_dict]
            new_oids = set(usage_dict) - set(left_good_oids + right_good_oids)
            # create left blocks from supplied ordering (left_oids)
            for oid in left_good_oids:
                # place blocks on the left side
                usage = usage_dict[oid]
                obj = (getattr(usage, 'component', None)
                       or getattr(usage, 'system', None))
                all_ports += getattr(obj, 'ports', [])
                p = QPointF(x_left, y_left_next)
                new_item = self.create_block(ObjectBlock, usage=usage, pos=p,
                                             right_ports=True)
                port_blocks.update(new_item.port_blocks)
                items.append(new_item)
                y_left_next += new_item.rect.height() + spacing
            for oid in right_good_oids:
                # place blocks on the right side
                usage = usage_dict[oid]
                obj = (getattr(usage, 'component', None)
                       or getattr(usage, 'system', None))
                all_ports += getattr(obj, 'ports', [])
                p = QPointF(x_right, y_right_next)
                new_item = self.create_block(ObjectBlock, usage=usage, pos=p,
                                             right_ports=False)
                port_blocks.update(new_item.port_blocks)
                items.append(new_item)
                y_right_next += new_item.rect.height() + spacing
            for oid in new_oids:
                # place blocks for any items in 'usages' but not in 'ordering'
                usage = usage_dict[oid]
                obj = (getattr(usage, 'component', None)
                       or getattr(usage, 'system', None))
                all_ports += getattr(obj, 'ports', [])
                if y_left_next <= y_right_next:
                    # if left column is shorter, put new block there ...
                    p = QPointF(x_left, y_left_next)
                    new_item = self.create_block(ObjectBlock, usage=usage,
                                                 pos=p, right_ports=True)
                    port_blocks.update(new_item.port_blocks)
                    items.append(new_item)
                    y_left_next += new_item.rect.height() + spacing
                else:
                    # otherwise, put new block in right column ...
                    p = QPointF(x_right, y_right_next)
                    new_item = self.create_block(ObjectBlock, usage=usage,
                                                 pos=p, right_ports=False)
                    port_blocks.update(new_item.port_blocks)
                    items.append(new_item)
                    y_right_next += new_item.rect.height() + spacing
        else:
            # no ordering is provided and the diagram currently has no blocks
            # -> place blocks in arbitrary order
            for usage in usages:
                obj = (getattr(usage, 'component', None)
                       or getattr(usage, 'system', None))
                all_ports += getattr(obj, 'ports', [])
                # orb.log.debug('  - creating block for "%s" ...' % obj.name)
                if i == 2.0:
                    left_col = right_ports = False
                    p = QPointF(x_right, y_right_next)
                    i = 1.0
                else:
                    left_col = right_ports = True
                    p = QPointF(x_left, y_left_next)
                    i += 1.0
                # orb.log.debug('    ... at position ({}, {}) ...'.format(
                                                            # p.x(), p.y()))
                new_item = self.create_block(ObjectBlock, usage=usage, pos=p,
                                             right_ports=right_ports)
                port_blocks.update(new_item.port_blocks)
                items.append(new_item)
                if left_col:
                    y_left_next += new_item.rect.height() + spacing
                else:
                    y_right_next += new_item.rect.height() + spacing
        # create subject block ...
        subj_block = self.create_ibd_subject_block(items)
        port_blocks.update(subj_block.port_blocks)
        # if Flows exist, create RoutedConnectors for them ...
        # subject might be a Project, so need getattr here ...
        flows = orb.search_exact(cname='Flow', flow_context=self.subject)
        orphaned_flow_oids = []
        if flows:
            # orb.log.debug('  - Flow objects found: {}'.format(
                                    # str([f.id for f in flows])))
            routing_channel = self.get_routing_channel()
            # orb.log.debug('  - creating routed connectors ...')
            for flow in flows:
                # check in case flows in db out of sync with diagram
                start_item = port_blocks.get(getattr(
                                             flow.start_port, 'oid', None))
                end_item = port_blocks.get(getattr(flow.end_port, 'oid', None))
                if not (start_item and end_item):
                    # NOTE: this indicates db/diagram out of sync ... delete
                    # this flow after finishing the diagram
                    orphaned_flow_oids.append(flow.oid)
                    continue
                # orb.log.debug('    + {}'.format(flow.id))
                connector = RoutedConnector(start_item, end_item,
                                            routing_channel,
                                            context=self.subject, pen_width=3)
                # orb.log.debug('      add to start and end ...')
                start_item.add_connector(connector)
                end_item.add_connector(connector)
                # orb.log.debug('      set z-value ...')
                connector.setZValue(-1000.0)
                # orb.log.debug('      add to scene ...')
                self.addItem(connector)
                # orb.log.debug('      update position.')
                connector.updatePosition()
        else:
            # orb.log.debug('  - no flows found')
            pass
        # set the upper left corner scene ...
        # orb.log.debug('  - centering scene in views ...')
        for n, view in enumerate(self.views()):
            # orb.log.debug('    view {}'.format(n))
            view.centerOn(0, 0)
        diagramz[self.subject.oid] = ordering
        orb._save_diagramz()
        # self.positions is used to test whether any block has been moved
        self.positions = self.get_block_positions()
        # delete any orphaned flows that were discovered
        for flow_oid in orphaned_flow_oids:
            flow = orb.get(flow_oid)
            if flow:
                assembly = flow.flow_context
                orb.delete([flow])
                dispatcher.send('deleted object', oid=flow_oid)
                assembly.mod_datetime = dtstamp()
                assembly.modifier = orb.get(state.get('local_user_oid'))
                orb.save([assembly])
                dispatcher.send('modified object', obj=assembly)


class DiagramView(QGraphicsView):
    """
    A view with a room.  :)
    """
    def __init__(self, subject, embedded=False, scene=None, parent=None):
        """
        Initialize.

        Args:
            subject (ManagedObject):  object that is the subject of the diagram

        Keyword Args:
            embedded (bool): flag to indicate the view is embedded and should
                not get an 'exit' menu item
            scene (DiagramScene): scene to be used
        """
        super().__init__()
        scene = scene or DiagramScene(subject, parent=self)
        self.setScene(scene)
        self.setSizePolicy(QSizePolicy.Expanding,
                           QSizePolicy.Expanding)
        self.setMinimumSize(300, 300)
        self.setAcceptDrops(True)

    def mimeTypes(self):
        return ["application/x-pgef-hardware-product",
                "application/x-pgef-port-type",
                "application/x-pgef-port-template"]

    def dragEnterEvent(self, event):
        if (event.mimeData().hasFormat(
                                "application/x-pgef-hardware-product")
            or event.mimeData().hasFormat(
                                "application/x-pgef-port-type")
            or event.mimeData().hasFormat(
                                "application/x-pgef-port-template")):
            event.accept()
        else:
            event.ignore()

