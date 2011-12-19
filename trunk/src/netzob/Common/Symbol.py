# -*- coding: utf-8 -*-



#+---------------------------------------------------------------------------+
#|         01001110 01100101 01110100 01111010 01101111 01100010             | 
#+---------------------------------------------------------------------------+
#| NETwork protocol modeliZatiOn By reverse engineering                      |
#| ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~+
#| @license      : GNU GPL v3                                                |
#| @copyright    : Georges Bossert and Frederic Guihery                      |
#| @url          : http://code.google.com/p/netzob/                          |
#| ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~+
#| @author       : {gbt,fgy}@amossys.fr                                      |
#| @organization : Amossys, http://www.amossys.fr                            |
#+---------------------------------------------------------------------------+

#+---------------------------------------------------------------------------+ 
#| Standard library imports
#+---------------------------------------------------------------------------+
import logging
import gtk
from operator import attrgetter
import re
import glib
from lxml.etree import ElementTree

#+---------------------------------------------------------------------------+
#| Local Imports
#+---------------------------------------------------------------------------+
from netzob.Common.Models.Factories.AbstractMessageFactory import AbstractMessageFactory
from netzob.Common.Field import Field
from netzob.Common.ProjectConfiguration import ProjectConfiguration
from netzob.Common.TypeIdentifier import TypeIdentifier
from netzob.Common.TypeConvertor import TypeConvertor

#+---------------------------------------------- 
#| C Imports
#+----------------------------------------------
import libNeedleman
from lxml import etree

#+---------------------------------------------------------------------------+
#| Symbol :
#|     Class definition of a symbol
#| @author     : {gbt,fgy}@amossys.fr
#| @version    : 0.2
#+---------------------------------------------------------------------------+
class Symbol(object):
    
    #+-----------------------------------------------------------------------+
    #| Constructor
    #+-----------------------------------------------------------------------+
    def __init__(self, id, name):
        self.id = id
        self.name = name
        self.alignment = ""
        self.score = 0.0
        self.messages = []
        self.fields = []
        
    
    #+---------------------------------------------- 
    #| buildRegexAndAlignment : compute regex and 
    #| self.alignment from the binary strings computed 
    #| in the C Needleman library
    #+----------------------------------------------
    def buildRegexAndAlignment(self, projectConfiguration):
        # Use the default protocol type for representation
        display = projectConfiguration.getVocabularyInferenceParameter(ProjectConfiguration.VOCABULARY_GLOBAL_DISPLAY)
        
        self.fields = []
        
        # If only one message (easy)
        if len(self.getMessages()) == 1 :
            field = Field("Field 0", 0, 0, self.getMessages()[0].getStringData(), display)
            self.addField(field)
            return
        
        # If more messages, we align them
        # Serialize the messages before sending them to the C library
        
        serialMessages = ""
        format = ""
        maxLeftReducedStringData = 0
        maxRightReducedStringData = 0
        maxReducedSize = 0
        for m in self.getMessages():
            format += str(len(m.getReducedStringData()) / 2) + "M"
            serialMessages += TypeConvertor.netzobRawToBinary(m.getReducedStringData())
            if m.getLeftReductionFactor() > maxLeftReducedStringData :
                maxLeftReducedStringData = m.getLeftReductionFactor()
            if m.getRightReductionFactor() > maxRightReducedStringData :
                maxRightReducedStringData = m.getRightReductionFactor()
            if m.getReducedSize() > maxReducedSize :
                maxReducedSize = m.getReducedSize()

        if projectConfiguration.getVocabularyInferenceParameter(ProjectConfiguration.VOCABULARY_DO_INTERNAL_SLICK) :
            doInternalSlick = 1
        else :
            doInternalSlick = 0
            
        # Align sequences in C library
        logging.debug("Alignment with : ")
        logging.debug("internal slick = " + str(doInternalSlick))
        logging.debug("len messages : " + str(len(self.getMessages())))
        logging.debug("format = " + format)
        logging.debug("serial = " + serialMessages)
        (score, aRegex, aMask) = libNeedleman.alignSequences(doInternalSlick, len(self.getMessages()), format, serialMessages)
        
        self.setScore(score)

        # Build alignment C library result
        align = ""
        i = 0
        for c in aMask:
            if c != '\x02':
                if c == '\x01':
                    align += "--"
                else:
                    align += aRegex[i:i + 1].encode("hex")
            i += 1
        
        if maxLeftReducedStringData > 0 :
            self.log.warning("add on the left part adding a bit of --")
            for i in range(0, maxReducedSize):
                align = "--" + align
        if maxRightReducedStringData > 0 :
            self.log.warning("add on the right part adding a bit of --")
            for i in range(0, maxReducedSize):
                align = align + "--"            

        self.setAlignment(align)
        # Initialized the self.fields structure based on alignement
        self.buildRegexFromAlignment(align, projectConfiguration)
    
    def buildRegexFromAlignment(self, align, projectConfiguration):
        # Build regex from alignment
        i = 0
        start = 0
        regex = []
        found = False
        for i in range(len(align)) :
            if (align[i] == "-"):                
                if (found == False) :
                    start = i
                    found = True
            else :
                if (found == True) :
                    found = False
                    nbTiret = i - start
                    regex.append("(.{," + str(nbTiret) + "})")
                    regex.append(align[i])
                else :
                    if len(regex) == 0:
                        regex.append(align[i])
                    else:
                        regex[-1] += align[i]
        if (found == True) :
            nbTiret = i - start
            regex.append("(.{," + str(nbTiret) + "})")

        # Use the default protocol type for representation
        display = projectConfiguration.getVocabularyInferenceParameter(ProjectConfiguration.VOCABULARY_GLOBAL_DISPLAY)

        iField = 0
        for regexElt in regex:
            field = Field("Field " + str(iField), 0, iField, regexElt, display)
            self.addField(field)
            iField = iField + 1

    #+---------------------------------------------- 
    #| Regex handling
    #+----------------------------------------------
    def refineRegexes(self):
        for field in self.getFields():
            tmpRegex = field.getRegex()
            if field.isRegexStatic():
                continue
            elif field.isRegexOnlyDynamic():
                cells = self.getMessagesValuesByField(field)
                min = 999999
                max = 0
                for cell in cells:
                    if len(cell) > max:
                        max = len(cell)
                    if len(cell) < min:
                        min = len(cell)
                if min == max:
                    field.setRegex("(.{" + str(min) + "})")
                else:
                    field.setRegex("(.{" + str(min) + "," + str(max) + "})")
            else:
                # TODO: handle complex regex
                continue

    

    
    #+---------------------------------------------- 
    #| getMessageByID:
    #|  Return the message which ID is provided
    #+----------------------------------------------
    def getMessageByID(self, messageID):
        for message in self.messages :
            if message.getID() == messageID :
                return message
            
        return None

    #+---------------------------------------------- 
    #| getFieldByIndex:
    #|  Return the field with specified index
    #+----------------------------------------------
    def getFieldByIndex(self, index):
        return self.fields[index]

    #+---------------------------------------------- 
    #| getMessagesValuesByField:
    #|  Return all the messages parts which are in 
    #|  the specified field
    #+----------------------------------------------
    def getMessagesValuesByField(self, field):
        # first we verify the field exists in the symbol
        if not field in self.fields :
            logging.warn("The computing field is not part of the current symbol")
            return []
        
        res = []
        for message in self.getMessages():
            messageTable = message.applyRegex()
            if len(messageTable) <= field.getIndex() :
                res.append("")
            else :
                messageElt = messageTable[field.getIndex()]
                res.append(messageElt)
        return res
    
    #+---------------------------------------------- 
    #| concatFields:
    #|  Concatenate two fields starting from iField
    #+----------------------------------------------
    def concatFields(self, iField):
        field1 = None
        field2 = None
        for field in self.fields :
            if field.getIndex() == iField :
                field1 = field
            elif field.getIndex() == iField + 1 :
                field2 = field
        # Build the merged regex
        newRegex = ""
        if field1.getRegex() == "":
            newRegex = field2.getRegex()
        if field2.getRegex() == "":
            newRegex = field1.getRegex()

        if field1.getRegex()[0] == "(" and field2.getRegex()[0] != "(": # Dyn + Static fields
            newRegex = field1.getRegex()[:-1] + field2.getRegex() + ")"

        if field1.getRegex()[0] != "(" and field2.getRegex()[0] == "(": # Static + Dyn fields
            newRegex = "(" + field1.getRegex() + field2.getRegex()[1:]

        if field1.getRegex()[0] == "(" and field2.getRegex()[0] == "(": # Dyn + Dyn fields
            newRegex = field1.getRegex()[:-1] + field2.getRegex()[1:]

        if field1.getRegex()[0] != "(" and field2.getRegex()[0] != "(": # Static + Static fields (should not happen...)
            newRegex = field1.getRegex() + field2.getRegex()

        # Default representation is BINARY
        new_name = field1.getName() + "+" + field2.getName()
        # Creation of the new Field
        newField = Field(new_name, 0, field1.getIndex(), newRegex, "binary")
        
        self.fields.remove(field1)
        self.fields.remove(field2)
        
        # Update the index of the fields placed after it
        for field in self.fields :
            if field.getIndex() > newField.getIndex() :
                field.setIndex(field.getIndex() - 1)
        self.fields.append(newField)
        # sort fields by their index
        self.fields = sorted(self.fields, key=attrgetter('index'), reverse=False)

    
    #+---------------------------------------------- 
    #| splitField:
    #|  Split a field in two fields
    #|  return False if the split does not occure, else True
    #+----------------------------------------------
    def splitField(self, field, split_position):
        if not (split_position > 0):
            return False
        
        # Find the static/dynamic cols
        cells = self.getMessagesValuesByField(field)
        ref1 = cells[0][:split_position]
        ref2 = cells[0][split_position:]
        isStatic1 = True
        isStatic2 = True
        lenDyn1 = len(cells[0][:split_position])
        lenDyn2 = len(cells[0][split_position:])
        for m in cells[1:]:
            if m[:split_position] != ref1:
                isStatic1 = False
                if len(m[:split_position]) > lenDyn1:
                    lenDyn1 = len(m[:split_position])
            if m[split_position:] != ref2:
                isStatic2 = False
                if len(m[split_position:]) > lenDyn2:
                    lenDyn2 = len(m[split_position:])

        # Build the new sub-regex
        if isStatic1:
            regex1 = ref1
        else:
            regex1 = "(.{," + str(lenDyn1) + "})"
        if isStatic2:
            regex2 = ref2
        else:
            regex2 = "(.{," + str(lenDyn2) + "})"

        if regex1 == "":
            return False
        if regex2 == "":
            return False

        new_type = field.getSelectedType()
        new_encapsulationLevel = field.getEncapsulationLevel()
        
        # We Build the two new fields
        field1 = Field("(1/2)" + field.getName(), new_encapsulationLevel, field.getIndex(), regex1, new_type)
        field1.setColor(field.getColor())
        if field.getDescription() != None and len(field.getDescription()) > 0 :
            field1.setDescription("(1/2) " + field.getDescription())
        field2 = Field("(2/2) " + field.getName(), new_encapsulationLevel, field.getIndex() + 1, regex2, new_type)
        field2.setColor(field.getColor())
        if field.getDescription() != None and len(field.getDescription()) > 0 :
            field2.setDescription("(2/2) " + field.getDescription())
        
        # Remove the truncated one
        self.fields.remove(field)
        
        # modify index to adapt 
        for field in self.getFields() :
            if field.getIndex() > field1.getIndex() :
                field.setIndex(field.getIndex() + 1)
        
        self.fields.append(field1)
        self.fields.append(field2)
        # sort fields by their index
        self.fields = sorted(self.fields, key=attrgetter('index'), reverse=False)
        
        return True
    
    #+-----------------------------------------------------------------------+
    #| getPossibleTypesForAField:
    #|     Retrieve all the possible types for a field
    #+-----------------------------------------------------------------------+
    def getPossibleTypesForAField(self, field):
        # first we verify the field exists in the symbol
        if not field in self.fields :
            logging.warn("The computing field is not part of the current symbol")
            return []
        
        # Retrieve all the part of the messages which are in the given field
        cells = self.getMessagesValuesByField(field)
        typeIdentifier = TypeIdentifier()        
        return typeIdentifier.getTypes(cells)
    
    #+-----------------------------------------------------------------------+
    #| getStyledPossibleTypesForAField:
    #|     Retrieve all the possibles types for a field and we colorize
    #|     the selected one we an HTML RED SPAN
    #+-----------------------------------------------------------------------+
    def getStyledPossibleTypesForAField(self, field):
        tmpTypes = self.getPossibleTypesForAField(field)
        for i in range(len(tmpTypes)):
            if tmpTypes[i] == field.getSelectedType():
                tmpTypes[i] = "<span foreground=\"red\">" + field.getSelectedType() + "</span>"
        return ", ".join(tmpTypes)
    
    
    #+---------------------------------------------- 
    #| dataCarving:
    #|  try to find semantic elements in each field
    #+----------------------------------------------    
    def dataCarving(self):
        if len(self.fields) == 0:
            return None

        vbox = gtk.VBox(False, spacing=5)
        vbox.show()
        hbox = gtk.HPaned()
        hbox.show()
        # Treeview containing potential data carving results ## ListStore format :
        # int: iField
        # str: data type (url, ip, email, etc.)
        store = gtk.ListStore(int, str)
        treeviewRes = gtk.TreeView(store)
        cell = gtk.CellRendererText()
        column = gtk.TreeViewColumn('Column')
        column.pack_start(cell, True)
        column.set_attributes(cell, text=0)
        treeviewRes.append_column(column)
        column = gtk.TreeViewColumn('Data type found')
        column.pack_start(cell, True)
        column.set_attributes(cell, text=1)
        treeviewRes.append_column(column)
        treeviewRes.set_size_request(200, 300)
        treeviewRes.show()
        scroll = gtk.ScrolledWindow()
        scroll.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scroll.show()
        scroll.add(treeviewRes)
        hbox.add(scroll)

        ## Algo : for each column, and then for each cell, try to carve data
        typer = TypeIdentifier()
        
        ## TODO: put this things in a dedicated class
        infoCarvers = {
            'url' : re.compile("((http:\/\/|https:\/\/)?(www\.)?(([a-zA-Z0-9\-]){2,}\.){1,4}([a-zA-Z]){2,6}(\/([a-zA-Z\-_\/\.0-9#:?+%=&;,])*)?)"),
            'email' : re.compile("[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,4}"),
            'ip' : re.compile("(((?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?))")
            }
        
        
        for field in self.getFields():
            for (carver, regex) in infoCarvers.items():
                matchElts = 0
                for cell in self.getMessagesValuesByField(field) :
                    for match in regex.finditer(TypeConvertor.netzobRawtoASCII(cell)):
                        matchElts += 1
                if matchElts > 0:
                    store.append([field, carver])

        # Preview of matching fields in a treeview ## ListStore format :
        # str: data
        treeview = gtk.TreeView(gtk.ListStore(str))
        cell = gtk.CellRendererText()
        column = gtk.TreeViewColumn('Data')
        column.pack_start(cell, True)
        column.set_attributes(cell, markup=0)
        treeview.append_column(column)
        treeview.set_size_request(700, 300)
        treeview.show()
        scroll = gtk.ScrolledWindow()
        scroll.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scroll.show()
        scroll.add(treeview)
        hbox.add(scroll)
        vbox.pack_start(hbox, True, True, 0)

        # Apply button
        but = gtk.Button(label="Apply data type on column")
        but.show()
        self.butDataCarvingHandle = None
        treeviewRes.connect("cursor-changed", self.dataCarvingResultSelected_cb, treeview, but, infoCarvers)
        vbox.pack_start(but, False, False, 0)

        return vbox
        # TODO : use hachoir to retrieve subfiles
        #    lines = os.popen("/usr/bin/hachoir-subfile " + target).readline()

    #+---------------------------------------------- 
    #| findSizeFields:
    #|  try to find the size fields of each regex
    #+----------------------------------------------    
    def findSizeFields(self, store):
        if len(self.fields) == 1:
            return
        iField = 0
        # We cover each field for a potential size field
        for field in self.getFields():
            if field.isRegexStatic(): # Means the element is static, and we exclude it for performance issue
                iField += 1
                continue
            cellsSize = self.getMessagesValuesByField(field)
            j = 0
            # We cover each field and aggregate them for a potential payload
            while j < len(self.getFields()):
                # Initialize the aggregate of messages from fieldJ to fieldK
                aggregateCellsData = []
                for l in range(len(cellsSize)):
                    aggregateCellsData.append("")

                # Fill the aggregate of messages and try to compare its length with the current expected length
                k = j
                while k < len(self.getFields()):
                    if k != j:
                        for l in range(len(cellsSize)):
                            aggregateCellsData[l] += self.getMessagesValuesByField(self.getFieldByIndex(k))[l]

                    # We try to aggregate the successive right sub-parts of j if it's a static column (TODO: handle dynamic column / TODO: handle left subparts of the K column)
                    if self.getFieldByIndex(j).isRegexStatic():
                        lenJ = len(self.getFieldByIndex(j).getRegex())
                        stop = 0
                    else:
                        lenJ = 2
                        stop = 0
                    for m in range(lenJ, stop, -2):
                        for n in [4, 0, 1]: # loop over different possible encoding of size field
                            res = True
                            for l in range(len(cellsSize)):
                                if self.getFieldByIndex(j).isRegexStatic():
                                    targetData = self.getFieldByIndex(j).getRegex()[lenJ - m:] + aggregateCellsData[l]
                                else:
                                    targetData = self.getMessagesValuesByField(self.getFieldByIndex(k))[l] + aggregateCellsData[l]

                                # Handle big and little endian for size field of 1, 2 and 4 octets length
                                rawMsgSize = TypeConvertor.netzobRawToBinary(cellsSize[l][:n * 2])
                                if len(rawMsgSize) == 1:
                                    expectedSizeType = "B"
                                elif len(rawMsgSize) == 2:
                                    expectedSizeType = "H"
                                elif len(rawMsgSize) == 4:
                                    expectedSizeType = "I"
                                else: # Do not consider size field with len > 4
                                    res = False
                                    break
                                (expectedSizeLE,) = struct.unpack("<" + expectedSizeType, rawMsgSize)
                                (expectedSizeBE,) = struct.unpack(">" + expectedSizeType, rawMsgSize)
                                if (expectedSizeLE != len(targetData) / 2) and (expectedSizeBE != len(targetData) / 2):
                                    res = False
                                    break
                            if res:
                                if self.getFieldByIndex(j).isRegexStatic(): # Means the regex j element is static and a sub-part is concerned
                                    store.append([self.id, iField, n * 2, j, lenJ - m, k, -1, "Group " + self.name + " : found potential size field (col " + str(iField) + "[:" + str(n * 2) + "]) for an aggregation of data field (col " + str(j) + "[" + str(lenJ - m) + ":] to col " + str(k) + ")"])
                                    self.log.info("In group " + self.name + " : found potential size field (col " + str(iField) + "[:" + str(n * 2) + "]) for an aggregation of data field (col " + str(j) + "[" + str(lenJ - m) + ":] to col " + str(k) + ")")
                                else:
                                    store.append([self.id, iField, n * 2, j, -1, k, -1, "Group " + self.name + " : found potential size field (col " + str(iField) + "[:" + str(n * 2) + "]) for an aggregation of data field (col " + str(j) + " to col " + str(k) + ")"])
                                    self.log.info("In group " + self.name + " : found potential size field (col " + str(iField) + "[:" + str(n * 2) + "]) for an aggregation of data field (col " + str(j) + " to col " + str(k) + ")")
                                break
                    k += 1
                j += 1
            iField += 1

    #+---------------------------------------------- 
    #| applyDataType_cb:
    #|  Called when user wants to apply a data type to a field
    #+----------------------------------------------
    def applyDataType_cb(self, button, iField, dataType):
        self.getFieldById(iField).setDescriptionByCol(dataType)

    #+---------------------------------------------- 
    #| dataCarvingResultSelected_cb:
    #|  Callback when clicking on a data carving result.
    #|  It shows a preview of the carved data
    #+----------------------------------------------
    def dataCarvingResultSelected_cb(self, treeview, treeviewTarget, but, infoCarvers):
        typer = TypeIdentifier()
        treeviewTarget.get_model().clear()
        (model, it) = treeview.get_selection().get_selected()
        if(it):
            if(model.iter_is_valid(it)):
                field = model.get_value(it, 0)
                dataType = model.get_value(it, 1)
                treeviewTarget.get_column(0).set_title("Field " + field.getIndex())
                if self.butDataCarvingHandle != None:
                    but.disconnect(self.butDataCarvingHandle)
                self.butDataCarvingHandle = but.connect("clicked", self.applyDataType_cb, field, dataType)
                for cell in self.getMessagesValuesByField(field) :
                    cell = glib.markup_escape_text(typer.toASCII(cell))
                    segments = []
                    for match in infoCarvers[dataType].finditer(cell):
                        if match == None:
                            treeviewTarget.get_model().append([ cell ])
                        segments.append((match.start(0), match.end(0)))

                    segments.reverse() # We start from the end to avoid shifting
                    for (start, end) in segments:
                        cell = cell[:end] + "</span>" + cell[end:]
                        cell = cell[:start] + '<span foreground="red" font_family="monospace">' + cell[start:]
                    treeviewTarget.get_model().append([ cell ])
    
    
    #+---------------------------------------------- 
    #| envDependencies:
    #|  try to find environmental dependencies
    #+----------------------------------------------    
    def envDependencies(self, project):
        if len(self.fields) == 0:
            return None

        vbox = gtk.VBox(False, spacing=5)
        vbox.show()
        hbox = gtk.HPaned()
        hbox.show()
        # Treeview containing potential data carving results ## ListStore format :
        # int: iField
        # str: env. dependancy name (ip, os, username, etc.)
        # str: env. dependancy value (127.0.0.1, Linux, john, etc.)
        store = gtk.ListStore(int, str, str)
        treeviewRes = gtk.TreeView(store)
        cell = gtk.CellRendererText()
        column = gtk.TreeViewColumn('Column')
        column.pack_start(cell, True)
        column.set_attributes(cell, text=0)
        treeviewRes.append_column(column)
        column = gtk.TreeViewColumn('Env. dependancy')
        column.pack_start(cell, True)
        column.set_attributes(cell, text=1)
        treeviewRes.append_column(column)
        treeviewRes.set_size_request(250, 300)
        treeviewRes.show()
        scroll = gtk.ScrolledWindow()
        scroll.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scroll.show()
        scroll.add(treeviewRes)
        hbox.add(scroll)

        ## Algo : for each column, and then for each cell, try to find environmental dependency
        
        for field in self.getFields():
            
            for envDependency in project.getConfiguration().getVocabularyInferenceParameter(ProjectConfiguration.VOCABULARY_ENVIRONMENTAL_DEPENDENCIES) :
                if envDependency.getValue() == "":
                    break
                matchElts = 0
                for cell in self.getMessagesValuesByField(field):
                    matchElts += TypeConvertor.netzobRawtoASCII(cell).count(envDependency.getValue())
                if matchElts > 0:
                    store.append([field, envDependency])

        # Preview of matching fields in a treeview ## ListStore format :
        # str: data
        treeview = gtk.TreeView(gtk.ListStore(str))
        cell = gtk.CellRendererText()
        column = gtk.TreeViewColumn('Data')
        column.pack_start(cell, True)
        column.set_attributes(cell, markup=0)
        treeview.append_column(column)
        treeview.set_size_request(700, 300)
        treeview.show()
        scroll = gtk.ScrolledWindow()
        scroll.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scroll.show()
        scroll.add(treeview)
        hbox.add(scroll)
        vbox.pack_start(hbox, True, True, 0)

        # Apply button
        but = gtk.Button(label="Apply data type on column")
        but.show()
        self.butDataCarvingHandle = None
        treeviewRes.connect("cursor-changed", self.envDependenciesResultSelected_cb, treeview, but)
        vbox.pack_start(but, False, False, 0)

        return vbox

    #+---------------------------------------------- 
    #| envDependenciesResultSelected_cb:
    #|  Callback when clicking on a environmental dependency result.
    #+----------------------------------------------
    def envDependenciesResultSelected_cb(self, treeview, treeviewTarget, but):
        treeviewTarget.get_model().clear()
        (model, it) = treeview.get_selection().get_selected()
        if(it):
            if(model.iter_is_valid(it)):
                field = model.get_value(it, 0)
                env = model.get_value(it, 1)
                treeviewTarget.get_column(0).set_title("Field " + field.getIndex())
                if self.butDataCarvingHandle != None:
                    but.disconnect(self.butDataCarvingHandle)
                self.butDataCarvingHandle = but.connect("clicked", self.applyDependency_cb, field, env)
                for cell in self.getMessagesValuesByField(field):
                    cell = glib.markup_escape_text(TypeConvertor.netzobRawtoASCII(cell))
                    pattern = re.compile(env.getValue(), re.IGNORECASE)
                    cell = pattern.sub('<span foreground="red" font_family="monospace">' + env.getValue() + "</span>", cell)
                    treeviewTarget.get_model().append([ cell ])

    #+---------------------------------------------- 
    #| applyDependency_cb:
    #|  Called when user wants to apply a dependency to a field
    #+----------------------------------------------
    def applyDependency_cb(self, button, iField, envName):
        self.getFieldById(iField).setDescriptionByCol(envName)
        pass
    
    #+---------------------------------------------- 
    #| removeMessage : remove any ref to the given
    #| message and recompute regex and score
    #+----------------------------------------------
    def removeMessage(self, message):
        self.messages.remove(message)
    
    def getID(self):
        return self.id
    
    def getMessages(self):
        return self.messages
    
    
    def getScore(self):
        return self.score
    
    def getName(self):
        return self.name
    
    def getFields(self):
        self.fields = sorted(self.fields, key=attrgetter('index'), reverse=False)
        return self.fields

    def setFields(self, fields):
        self.fields = fields
        
    def addMessage(self, message):
        for msg in self.messages :
            if msg.getID() == message.getID() :
                return
        message.setSymbol(self)
        self.messages.append(message)
        
    def addField(self, field):
        self.fields.append(field)
    def getAlignment(self):
        return self.alignment.strip()
    def setAlignment(self, alignment):
        self.alignment = alignment
    def setScore(self, score):
        self.score = score
    def setName(self, name):
        self.name = name
        
    
    def save(self, root, namespace):
        xmlSymbol = etree.SubElement(root, "{" + namespace + "}symbol")
        xmlSymbol.set("alignment", str(self.getAlignment()))
        xmlSymbol.set("id", str(self.getID()))
        xmlSymbol.set("name", str(self.getName()))
        xmlSymbol.set("score", str(self.getScore()))
        
        # Save the messages
        xmlMessages = etree.SubElement(xmlSymbol, "{" + namespace + "}messages")
        for message in self.messages :
            AbstractMessageFactory.save(message, xmlMessages, namespace)
        # Save the fields
        xmlFields = etree.SubElement(xmlSymbol, "{" + namespace + "}fields")
        for field in self.getFields() :
            field.save(xmlFields, namespace)
        
    @staticmethod
    def loadSymbol(xmlRoot, namespace, version):
        
        if version == "0.1" :
            nameSymbol = xmlRoot.get("name")
            idSymbol = xmlRoot.get("id")
            alignmentSymbol = xmlRoot.get("alignment", None)
            scoreSymbol = float(xmlRoot.get("score", "0"))
            
            symbol = Symbol(idSymbol, nameSymbol)
            symbol.setAlignment(alignmentSymbol)
            symbol.setScore(scoreSymbol)
            
            # we parse the messages
            if xmlRoot.find("{" + namespace + "}messages") != None :
                xmlMessages = xmlRoot.find("{" + namespace + "}messages")
                for xmlMessage in xmlMessages.findall("{" + namespace + "}message") :
                    message = AbstractMessageFactory.loadFromXML(xmlMessage, namespace, version)
                    if message != None :
                        message.setSymbol(symbol)
                        symbol.addMessage(message)
                        
            # we parse the fields
            if xmlRoot.find("{" + namespace + "}fields") != None :
                xmlFields = xmlRoot.find("{" + namespace + "}fields")
                for xmlField in xmlFields.findall("{" + namespace + "}field") :
                    field = Field.loadFromXML(xmlField, namespace, version)
                    if field != None :
                        symbol.addField(field)
            return symbol
        return None
        
        
        
        