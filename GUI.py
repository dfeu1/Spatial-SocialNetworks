from collections import Counter
import os
from os.path import exists
from os import getenv
import random
import threading
from anytree import Node, RenderTree, find_by_attr
from Config import Config
from PyQt5 import QtGui, QtCore
from PyQt5.QtCore import QTimer
from scipy import spatial
import pyqtgraph as pg
import PyQt5.QtWidgets as QtWidgets
from PyQt5.QtWebEngineWidgets import QWebEngineView
from RoadNetwork import RoadNetwork
from SocialNetwork import SocialNetwork
from BitVectorCommunityDetector import BitVectorCommunityDetector
from CommunityBridge import CommunityBridge
from CommunityScorer import CommunityScorer
from sklearn.cluster import KMeans
from pyvis.network import Network
import networkx as nx
import time
from gui.menubar import MenuBar
from gui.queryInput import QueryInput
from gui.user import UserUI
from gui.toolbar import Toolbar, QueryToolbar, Timeline
from gui.tree import Mixin as TreeMixin
import datetime
import time
import json


class Gui(QtWidgets.QMainWindow, TreeMixin):

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            print('Creating the object')
            cls._instance = super(Gui, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        super(Gui, self).__init__()
        # Creates config
        self.config = Config()
        # Plot options
        pg.setConfigOptions(antialias=True)
        pg.setConfigOption('background', 'white')
        # A dictionary of windows, each window has it's on id
        self.__windows = {}
        # Stores file hierarchy data
        self.__fileTreeObjects = {}
        # Stores timestamps for query time calculation
        self.Qstart = 0
        self.Qend = 0
        self.SummaryResponseTime = 0
        # Stores timestamps for query time calculation
        self.CTstart = 0
        self.CTend = 0
        self.ClusterResponseTime = 0
        # Stores widget instances
        self.roadGraphWidget = None
        self.socialGraphWidget = None
        self.socialNetWidget = QWebEngineView()
        self.summarySelected = False
        self.hidePOIsSelected = False
        # Stores selected network instances
        self.selectedRoadNetwork = None
        self.selectedSocialNetwork = None
        # Query user information
        self.queryUser = None
        self.queryKeyword = None
        self.queryUserPlots = []
        # Store data for interactive network
        self.interactiveNetwork = nx.Graph()
        # Store all network info in dict format {"NetworkName: {"Data": "Value", ...}, ..."}
        self.__roadNetworks = self.config.settings["Road Networks"]
        self.__socialNetworks = self.config.settings["Social Networks"]
        # Store network objects
        self.__roadNetworkObjs = self.createNetworkInstances(self.__roadNetworks, RoadNetwork)
        self.__socialNetworkObjs = self.createNetworkInstances(self.__socialNetworks, SocialNetwork)
        # Set up layout
        self.layout = QtWidgets.QGridLayout(self)
        self.layout.setSpacing(0)
        self.sumLayout = QtWidgets.QGridLayout(self)
        self.sumLayout.setSpacing(0)
        self.view = QtWidgets.QWidget()
        # Initializes menus
        self.__menuBar()
        #self.navToolbar()
        #self.__queryUserButton()
        self.__mainWindow()
        self.__ViewStats()
        # Array for plot points
        self.centers = []
        self.ids = []

        self.toolbar = Toolbar(self)
        self.__windows[3] = QtWidgets.QWidget()
        self.__windows[4] = QtWidgets.QWidget()
        self.__windows[6] = QtWidgets.QWidget()
        self.__windows[7] = QtWidgets.QWidget()
        self.queryInput = QueryInput(self, self.__windows[3], self.__windows[6])
        self.queryUserToolbar = QueryToolbar(self, self.__windows[3], self.__windows[4])
        self.queryUserToolbar.queryUserButton()
        self.toolbar.navToolbar()
        self.timeline = Timeline(self)
        self.timeline.hide()
        self.__queryFrames = []
        self.playAnimation = False

        self.communityUserPos = {}
        self.previousUsers = []
        
        # Initialize community detector
        self.communityDetector = None
        
        # Initialize community bridge for original functionality
        self.community_bridge = CommunityBridge(self)
        
        # Storage for community results
        self.current_communities = []
        
        # Store scoring weights
        self.current_scoring_weights = {
            'keyword': 0.4,
            'distance': 0.3,
            'connection': 0.3
        }


    # Creates the plot widgets. suffix is used when a summary graph is created, for example
    def createPlots(self, suffix=""):
        # Create a layout with two columns of equal width
        self.win.ci.layout.setColumnStretchFactor(0, 1)
        self.win.ci.layout.setColumnStretchFactor(1, 1)
        
        # Add social network plot to the left column
        self.socialGraphWidget = self.win.addPlot(row=0, col=0, title=f"Social Network {suffix}")
        self.socialGraphWidget.setAspectLocked(True)
        self.socialGraphWidget.showGrid(x=True, y=True)
        self.socialGraphWidget.setMouseEnabled(x=True, y=True)
        
        # Add road network plot to the right column
        self.roadGraphWidget = self.win.addPlot(row=0, col=1, title=f"Road Network {suffix}")
        self.roadGraphWidget.scene().sigMouseClicked.connect(self.roadGraphClick)
        self.roadGraphWidget.setMouseEnabled(x=True, y=True)
        
        # Link the axes of both plots for synchronized zooming/panning
        self.socialGraphWidget.setXLink(self.roadGraphWidget)
        self.socialGraphWidget.setYLink(self.roadGraphWidget)
        
        # Ensure both plots are visible and properly sized
        self.win.ci.layout.setSpacing(10)
        self.socialGraphWidget.show()
        self.roadGraphWidget.show()

    def roadGraphClick(self, event):
        vb = self.roadGraphWidget.vb
        cords = event.scenePos()
        if self.roadGraphWidget.sceneBoundingRect().contains(cords):
            point = vb.mapSceneToView(cords)
            if len(self.centers) > 0:
                centers_array = [[x, y] for x, y in self.centers]
                tree = spatial.KDTree(centers_array)
                closest_point = tree.query([[point.x(), point.y()]])[1][0]
                ui = UserUI(self, self.__windows[7])
                ui.showClusterUsers(self.selectedSocialNetwork.getClusterUsers(self.ids[closest_point]))

    def createSumPlot(self, suffix=None):
        self.roadGraphWidget = self.win.addPlot(row=0, col=1, title=f"Road Network {suffix}")

    # Displays main window
    def __mainWindow(self):
        # Set up window
        screensize = self.screen().availableSize().width(), self.screen().availableSize().height()
        self.setGeometry(int((screensize[0] / 2) - 500), int((screensize[1] / 2) - 300), 1000, 600)
        self.setWindowTitle("Spatial-Social Networks") 
        self.setWindowIcon(QtGui.QIcon('Assets/favicon.ico'))
        self.win = pg.GraphicsLayoutWidget()
        self.sum = pg.GraphicsLayoutWidget()
        with open('nx.html', 'r') as f:
            html = f.read()
            self.socialNetWidget.setHtml(html)
        # Define default layout
        self.layout.addWidget(self.win, 0, 0, 1, 2)
        # self.toolbar.navToolbar()
        self.view.setLayout(self.layout)
        self.setCentralWidget(self.view)
        # Create and set up graph widget
        self.createPlots()
        # Show window
        self.show()
    
    def initializeCommunityDetector(self):
        """Initialize or update the community detector with current networks"""
        if self.selectedSocialNetwork and self.selectedRoadNetwork:
            # Get weights from dialog if it exists
            keyword_weight = 0.4
            distance_weight = 0.3
            connection_weight = 0.3
            
            if hasattr(self, 'bitvectorDialog') and self.__windows.get(9) is not None:
                # Get values from sliders
                keyword_weight = self.__windows[9].keywordWeightSlider.value() / 100
                distance_weight = self.__windows[9].distanceWeightSlider.value() / 100
                connection_weight = self.__windows[9].connectionWeightSlider.value() / 100
                
                # Normalize weights
                total = keyword_weight + distance_weight + connection_weight
                if total > 0:
                    keyword_weight = keyword_weight / total
                    distance_weight = distance_weight / total
                    connection_weight = connection_weight / total
            
            self.communityDetector = BitVectorCommunityDetector(
                self.selectedSocialNetwork, 
                self.selectedRoadNetwork,
                keyword_weight=keyword_weight,
                distance_weight=distance_weight,
                connection_weight=connection_weight
            )
            self.precomputed = False
            
            # Update current scoring weights
            self.current_scoring_weights = {
                'keyword': keyword_weight,
                'distance': distance_weight,
                'connection': connection_weight
            }
            
            return True
        return False

    def visualize_social_network(self, community_members=None):
        if community_members:
            # Extract user IDs from community_members
            community_users = []
            for community in community_members:
                if isinstance(community, dict) and 'users' in community:
                    community_users.extend(community['users'])
            all_users = set(community_users)  # Avoid duplicates
        else:
            # Get all users and their locations
            all_users = self.selectedSocialNetwork.getUsers()

        plotted_users = {}

        # Plot user nodes
        for user in all_users:
            if isinstance(user, str):  # Ensure user is a valid string ID
                try:
                    loc = self.selectedSocialNetwork.userLoc(user)
                    # ...existing code for plotting users...
                except KeyError:
                    print(f"User location not found for user ID: {user}")

    def __bitvectorCommunitySearch(self):
        """Open dialog for community search with bit vector optimization"""
        # Check if networks are available first
        if not self.selectedSocialNetwork or not self.selectedRoadNetwork:
            QtWidgets.QMessageBox.warning(
                self,
                "Networks Required",
                "Both social and road networks must be selected."
            )
            return
            
        # Initialize community detector automatically
        self.initializeCommunityDetector()
            
        # Create dialog if it doesn't exist
        if not hasattr(self, 'bitvectorDialog') or self.__windows.get(9) is None:
            self.__windows[9] = QtWidgets.QDialog(self)
            self.__windows[9].setWindowTitle("BitVector Community Search")
            self.__windows[9].setWindowModality(QtCore.Qt.ApplicationModal)
            self.__windows[9].resize(500, 550)  # Increased size for additional parameters
            
            # Main layout
            layout = QtWidgets.QVBoxLayout(self.__windows[9])
            
            # Form layout for inputs
            form = QtWidgets.QFormLayout()
            
            # Query mode selection
            self.__windows[9].queryModeGroup = QtWidgets.QGroupBox("Query Mode")
            queryModeLayout = QtWidgets.QVBoxLayout()
            
            # Radio buttons for query mode
            self.__windows[9].userModeRadio = QtWidgets.QRadioButton("Use Selected User")
            self.__windows[9].keywordModeRadio = QtWidgets.QRadioButton("Enter Keywords Directly")
            
            # Set default mode based on whether a user is selected
            if self.queryUser is not None:
                self.__windows[9].userModeRadio.setChecked(True)
            else:
                self.__windows[9].keywordModeRadio.setChecked(True)
            
            queryModeLayout.addWidget(self.__windows[9].userModeRadio)
            queryModeLayout.addWidget(self.__windows[9].keywordModeRadio)
            self.__windows[9].queryModeGroup.setLayout(queryModeLayout)
            form.addRow(self.__windows[9].queryModeGroup)
            
            # User mode widgets
            self.__windows[9].userModeWidget = QtWidgets.QWidget()
            userModeLayout = QtWidgets.QVBoxLayout(self.__windows[9].userModeWidget)
            userModeLayout.setContentsMargins(0, 0, 0, 0)
            
            # Query user information display
            if self.queryUser is not None:
                self.__windows[9].queryUserLabel = QtWidgets.QLabel(f"Query User: {self.queryUser[0]}")
                self.__windows[9].queryUserLabel.setStyleSheet("font-weight: bold;")
                userModeLayout.addWidget(self.__windows[9].queryUserLabel)
                
                # Keywords display (read-only)
                query_keywords = self.selectedSocialNetwork.getUserKeywords(self.queryUser[0])
                keywords_text = ", ".join([self.selectedSocialNetwork.getKeywordByID(k) for k in query_keywords])
                
                self.__windows[9].keywordsDisplay = QtWidgets.QTextEdit()
                self.__windows[9].keywordsDisplay.setText(keywords_text)
                self.__windows[9].keywordsDisplay.setReadOnly(True)
                self.__windows[9].keywordsDisplay.setMaximumHeight(60)
                userModeLayout.addWidget(QtWidgets.QLabel("User's Keywords:"))
                userModeLayout.addWidget(self.__windows[9].keywordsDisplay)
            else:
                self.__windows[9].queryUserLabel = QtWidgets.QLabel("No user selected")
                self.__windows[9].queryUserLabel.setStyleSheet("font-weight: bold; color: red;")
                userModeLayout.addWidget(self.__windows[9].queryUserLabel)
            
            form.addRow("User Info:", self.__windows[9].userModeWidget)
            
            # Keyword mode widgets
            self.__windows[9].keywordModeWidget = QtWidgets.QWidget()
            keywordModeLayout = QtWidgets.QVBoxLayout(self.__windows[9].keywordModeWidget)
            keywordModeLayout.setContentsMargins(0, 0, 0, 0)
            
            # Direct keyword input
            keywordModeLayout.addWidget(QtWidgets.QLabel("Enter keywords separated by commas:"))
            self.__windows[9].keywordInput = QtWidgets.QTextEdit()
            self.__windows[9].keywordInput.setMaximumHeight(60)
            self.__windows[9].keywordInput.setPlaceholderText("e.g., selfie, love, nature, techie")
            keywordModeLayout.addWidget(self.__windows[9].keywordInput)
            
            # Add keyword lookup button
            self.__windows[9].keywordLookupBtn = QtWidgets.QPushButton("Lookup Keywords")
            self.__windows[9].keywordLookupBtn.clicked.connect(self.lookupKeywords)
            keywordModeLayout.addWidget(self.__windows[9].keywordLookupBtn)
            
            form.addRow("Direct Input:", self.__windows[9].keywordModeWidget)
            
            # Connect radio buttons to show/hide appropriate widgets
            def updateQueryMode():
                self.__windows[9].userModeWidget.setVisible(self.__windows[9].userModeRadio.isChecked())
                self.__windows[9].keywordModeWidget.setVisible(self.__windows[9].keywordModeRadio.isChecked())
            
            self.__windows[9].userModeRadio.toggled.connect(updateQueryMode)
            updateQueryMode()
            
            # Top-K communities input
            self.__windows[9].topKInput = QtWidgets.QSpinBox()
            self.__windows[9].topKInput.setRange(1, 20)
            self.__windows[9].topKInput.setValue(5)
            form.addRow("Number of Communities (K):", self.__windows[9].topKInput)
            
            # Radius selection
            self.__windows[9].radiusCombo = QtWidgets.QComboBox()
            self.__windows[9].radiusCombo.addItems(["1", "2"])
            self.__windows[9].radiusCombo.setCurrentIndex(1)  # Default to r=2
            form.addRow("Radius (r):", self.__windows[9].radiusCombo)
            
            # Minimum similarity
            self.__windows[9].minSimInput = QtWidgets.QDoubleSpinBox()
            self.__windows[9].minSimInput.setRange(0.01, 0.5)
            self.__windows[9].minSimInput.setSingleStep(0.01)
            self.__windows[9].minSimInput.setValue(0.01)
            form.addRow("Minimum Similarity:", self.__windows[9].minSimInput)
            
            scoring_header = QtWidgets.QLabel("Scoring Weights")
            scoring_header.setStyleSheet("font-weight: bold; margin-top: 10px;")
            form.addRow(scoring_header)
            
            def create_weight_slider(default_value=0.33):
                slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
                slider.setRange(1, 100)
                slider.setValue(int(default_value * 100))
                slider.setTickPosition(QtWidgets.QSlider.TicksBelow)
                slider.setTickInterval(10)
                
                value_label = QtWidgets.QLabel(f"{default_value:.2f}")
                
                slider.valueChanged.connect(lambda v: value_label.setText(f"{v}%"))
                
                # Create layout for slider and label
                slider_layout = QtWidgets.QHBoxLayout()
                slider_layout.addWidget(slider)
                slider_layout.addWidget(value_label)
                
                return slider_layout, slider
            
            # Keyword weight slider (default: 0.4)
            keyword_layout, self.__windows[9].keywordWeightSlider = create_weight_slider(0.4)
            form.addRow("Keyword Weight:", keyword_layout)
            
            # Distance weight slider (default: 0.3)
            distance_layout, self.__windows[9].distanceWeightSlider = create_weight_slider(0.3)
            form.addRow("Distance Weight:", distance_layout)
            
            # Connection weight slider (default: 0.3)
            connection_layout, self.__windows[9].connectionWeightSlider = create_weight_slider(0.3)
            form.addRow("Connection Weight:", connection_layout)
            
            # Helper function for weight normalization
            def normalize_weights():
                # Get current values
                kw = self.__windows[9].keywordWeightSlider.value() / 100
                dw = self.__windows[9].distanceWeightSlider.value() / 100
                cw = self.__windows[9].connectionWeightSlider.value() / 100
                
                # Normalize to sum to 1
                total = kw + dw + cw
                if total > 0:
                    kw = kw / total
                    dw = dw / total
                    cw = cw / total
                
                # Update sliders without triggering their signals
                self.__windows[9].keywordWeightSlider.blockSignals(True)
                self.__windows[9].distanceWeightSlider.blockSignals(True)
                self.__windows[9].connectionWeightSlider.blockSignals(True)
                
                self.__windows[9].keywordWeightSlider.setValue(int(kw * 100))
                self.__windows[9].distanceWeightSlider.setValue(int(dw * 100))
                self.__windows[9].connectionWeightSlider.setValue(int(cw * 100))
                
                self.__windows[9].keywordWeightSlider.blockSignals(False)
                self.__windows[9].distanceWeightSlider.blockSignals(False)
                self.__windows[9].connectionWeightSlider.blockSignals(False)
                
                # Update labels
                self.__windows[9].keywordWeightSlider.valueChanged.emit(self.__windows[9].keywordWeightSlider.value())
                self.__windows[9].distanceWeightSlider.valueChanged.emit(self.__windows[9].distanceWeightSlider.value())
                self.__windows[9].connectionWeightSlider.valueChanged.emit(self.__windows[9].connectionWeightSlider.value())
            
            # Add normalize button
            normalize_btn = QtWidgets.QPushButton("Normalize Weights")
            normalize_btn.clicked.connect(normalize_weights)
            form.addRow("", normalize_btn)
            
            # Add section header for Optimization
            optimization_header = QtWidgets.QLabel("Optimization Settings")
            optimization_header.setStyleSheet("font-weight: bold; margin-top: 10px;")
            form.addRow(optimization_header)
            
            # Precomputation is now handled automatically in the background
            
            # BitVector Tree optimization
            self.__windows[9].treeOptCheck = QtWidgets.QCheckBox("Use BitVector Tree")
            self.__windows[9].treeOptCheck.setChecked(False)
            self.__windows[9].buildTreeBtn = QtWidgets.QPushButton("Build Tree Now")
            self.__windows[9].buildTreeBtn.clicked.connect(self.buildBitVectorTree)
            treeOptFrame = QtWidgets.QHBoxLayout()
            treeOptFrame.addWidget(self.__windows[9].treeOptCheck)
            treeOptFrame.addWidget(self.__windows[9].buildTreeBtn)
            form.addRow("Tree Optimization:", treeOptFrame)
            
            # Status label
            self.__windows[9].statusLabel = QtWidgets.QLabel("Ready")
            self.__windows[9].statusLabel.setAlignment(QtCore.Qt.AlignCenter)
            
            # Buttons
            buttonBox = QtWidgets.QHBoxLayout()
            self.__windows[9].searchBtn = QtWidgets.QPushButton("Find Communities")
            self.__windows[9].searchBtn.clicked.connect(self.findCommunities)
            self.__windows[9].cancelBtn = QtWidgets.QPushButton("Cancel")
            self.__windows[9].cancelBtn.clicked.connect(self.__windows[9].reject)
            buttonBox.addWidget(self.__windows[9].searchBtn)
            buttonBox.addWidget(self.__windows[9].cancelBtn)
            
            # Add to main layout
            layout.addLayout(form)
            layout.addWidget(self.__windows[9].statusLabel)
            layout.addLayout(buttonBox)
        else:
            if hasattr(self.__windows[9], 'userModeRadio'):
                if self.queryUser is not None:
                    self.__windows[9].queryUserLabel.setText(f"Query User: {self.queryUser[0]}")
                    self.__windows[9].queryUserLabel.setStyleSheet("font-weight: bold;")
                    
                    query_keywords = self.selectedSocialNetwork.getUserKeywords(self.queryUser[0])
                    keywords_text = ", ".join([self.selectedSocialNetwork.getKeywordByID(k) for k in query_keywords])
                    self.__windows[9].keywordsDisplay.setText(keywords_text)
                    
                    # Enable user mode if a user is selected
                    self.__windows[9].userModeRadio.setEnabled(True)
                    self.__windows[9].userModeRadio.setChecked(True)
                else:
                    self.__windows[9].queryUserLabel.setText("No user selected")
                    self.__windows[9].queryUserLabel.setStyleSheet("font-weight: bold; color: red;")
                    
                    # Disable user mode if no user is selected
                    self.__windows[9].userModeRadio.setEnabled(False)
                    self.__windows[9].keywordModeRadio.setChecked(True)
        
        # Check if networks are available
        if not self.selectedSocialNetwork or not self.selectedRoadNetwork:
            QtWidgets.QMessageBox.warning(
                self,
                "Networks Required",
                "Both social and road networks must be selected."
            )
            return
        
        # Initialize detector if needed
        if not self.communityDetector:
            self.initializeCommunityDetector()
        
        # Show dialog
        self.__windows[9].show()
        
    def lookupKeywords(self):
        """Show available keywords in the system for reference and allow selection"""
        if not self.selectedSocialNetwork:
            QtWidgets.QMessageBox.warning(
                self,
                "Social Network Required",
                "Please select a social network first."
            )
            return
            
        # Create a dialog to display available keywords
        keywordDialog = QtWidgets.QDialog(self)
        keywordDialog.setWindowTitle("Available Keywords")
        keywordDialog.setWindowModality(QtCore.Qt.ApplicationModal)
        keywordDialog.resize(400, 500)
        
        # Main layout
        layout = QtWidgets.QVBoxLayout(keywordDialog)
        
        # Get all keywords from the keyword map
        all_keywords = {}
        for keyword_id, keyword in self.selectedSocialNetwork._SocialNetwork__keywordMap.items():
            all_keywords[keyword] = keyword_id
        
        # Create a list widget to display keywords
        keywordList = QtWidgets.QListWidget()
        keywordList.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        for keyword in sorted(all_keywords.keys()):
            keywordList.addItem(f"{keyword} (ID: {all_keywords[keyword]})")
        
        # Add search box
        searchBox = QtWidgets.QLineEdit()
        searchBox.setPlaceholderText("Search keywords...")
        
        def filterKeywords():
            search_text = searchBox.text().lower()
            for i in range(keywordList.count()):
                item = keywordList.item(i)
                item.setHidden(search_text not in item.text().lower())
        
        searchBox.textChanged.connect(filterKeywords)
        
        # Function to add selected keyword on double-click
        def addKeywordOnDoubleClick(item):
            keyword_text = item.text().split(" (ID:")[0]
            current_text = self.__windows[9].keywordInput.toPlainText().strip()
            
            if current_text:
                # Add comma if there's already text
                self.__windows[9].keywordInput.setPlainText(f"{current_text}, {keyword_text}")
            else:
                self.__windows[9].keywordInput.setPlainText(keyword_text)
        
        keywordList.itemDoubleClicked.connect(addKeywordOnDoubleClick)
        
        # Add widgets to layout
        layout.addWidget(QtWidgets.QLabel("Search:"))
        layout.addWidget(searchBox)
        layout.addWidget(QtWidgets.QLabel(f"Available Keywords ({len(all_keywords)}):"))
        layout.addWidget(QtWidgets.QLabel("Double-click to add a keyword or select multiple and click OK"))
        layout.addWidget(keywordList)
        
        # Add buttons
        buttonBox = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok)
        
        # Function to add selected keywords when OK is clicked
        def addSelectedKeywords():
            selected_items = keywordList.selectedItems()
            if selected_items:
                selected_keywords = [item.text().split(" (ID:")[0] for item in selected_items]
                current_text = self.__windows[9].keywordInput.toPlainText().strip()
                
                if current_text:
                    # Add comma if there's already text
                    new_text = current_text + ", " + ", ".join(selected_keywords)
                else:
                    new_text = ", ".join(selected_keywords)
                    
                self.__windows[9].keywordInput.setPlainText(new_text)
            
            keywordDialog.accept()
        
        # Safely disconnect the signal using try-except to handle the case when there are no connections
        try:
            buttonBox.accepted.disconnect()
        except TypeError:
            # No connections to disconnect, which is fine
            pass
        buttonBox.accepted.connect(addSelectedKeywords)
        layout.addWidget(buttonBox)
        
        # Show dialog
        keywordDialog.exec_()

    def buildBitVectorTree(self):
        """Build bit vector tree for optimization"""
        # Check if networks are available
        if not self.communityDetector:
            if not self.initializeCommunityDetector():
                QtWidgets.QMessageBox.warning(
                    self,
                    "Networks Required",
                    "Both social and road networks must be selected."
                )
                return
        
        # Update status
        self.__windows[9].statusLabel.setText("Building BitVector Tree... This may take several minutes.")
        self.__windows[9].buildTreeBtn.setEnabled(False)
        self.__windows[9].searchBtn.setEnabled(False)
        self.__windows[9].repaint()  # Force UI update
        
        # Build tree
        try:
            self.communityDetector.build_bit_vector_tree()
            # Automatically save tree to tree.json
            self.communityDetector.save_tree('tree.json')
            self.__windows[9].statusLabel.setText("BitVector Tree built and saved successfully!")
        except Exception as e:
            self.__windows[9].statusLabel.setText(f"Error: {str(e)}")
        
        # Re-enable buttons
        self.__windows[9].buildTreeBtn.setEnabled(True)
        self.__windows[9].searchBtn.setEnabled(True)

    def saveTreeToFile(self):
        """Save BitVector tree to a user-specified file"""
        if not self.communityDetector or not self.communityDetector.tree_built:
            QtWidgets.QMessageBox.warning(
                self,
                "Tree Not Built",
                "Please build the BitVector tree first."
            )
            return

        # Open file dialog
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save BitVector Tree",
            "",
            "JSON Files (*.json);;All Files (*)"
        )

        if file_path:
            try:
                self.communityDetector.save_tree(file_path)
                self.__windows[9].statusLabel.setText(f"Tree saved successfully to {file_path}")
            except Exception as e:
                QtWidgets.QMessageBox.critical(
                    self,
                    "Save Error",
                    f"Failed to save tree: {str(e)}"
                )

    def loadTreeFromFile(self):
        """Load BitVector tree from a user-specified file"""
        # Open file dialog
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Load BitVector Tree",
            "",
            "JSON Files (*.json);;All Files (*)"
        )

        if file_path:
            try:
                if not self.communityDetector:
                    if not self.initializeCommunityDetector():
                        return

                success = self.communityDetector.load_tree(file_path)
                if success:
                    self.__windows[9].statusLabel.setText(f"Tree loaded successfully from {file_path}")
                    self.__windows[9].saveTreeBtn.setEnabled(True)
                    self.__windows[9].treeOptCheck.setChecked(True)
                else:
                    QtWidgets.QMessageBox.warning(
                        self,
                        "Load Failed",
                        "Failed to load the tree file. The file may be corrupted or invalid."
                    )
            except Exception as e:
                QtWidgets.QMessageBox.critical(
                    self,
                    "Load Error",
                    f"Failed to load tree: {str(e)}"
                )

    def precomputeSubgraphs(self):
        """Precompute subgraphs for faster community detection"""
        # Check if networks are available
        if not self.communityDetector:
            if not self.initializeCommunityDetector():
                QtWidgets.QMessageBox.warning(
                    self,
                    "Networks Required",
                    "Both social and road networks must be selected."
                )
                return
        
        # Update status
        self.__windows[9].statusLabel.setText("Precomputing... This may take several minutes.")
        self.__windows[9].precompBtn.setEnabled(False)
        self.__windows[9].searchBtn.setEnabled(False)
        self.__windows[9].repaint()  # Force UI update
        
        # Perform precomputation
        try:
            # Start with r=1 (faster)
            self.communityDetector.precompute_radius_subgraphs(radius=1, verbose=True)
            
            # Then do r=2
            self.communityDetector.precompute_radius_subgraphs(radius=2, verbose=True)
            
            # Update state
            self.precomputed = True
            self.__windows[9].precompCheck.setChecked(True)
            self.__windows[9].statusLabel.setText("Precomputation complete!")
            
        except Exception as e:
            self.__windows[9].statusLabel.setText(f"Error: {str(e)}")
        
        # Re-enable buttons
        self.__windows[9].precompBtn.setEnabled(True)
        self.__windows[9].searchBtn.setEnabled(True)

    def findCommunities(self):
        """Find communities using bit vector optimization"""
        # Check if networks are available
        if not self.communityDetector:
            if not self.initializeCommunityDetector():
                QtWidgets.QMessageBox.warning(
                    self,
                    "Networks Required",
                    "Both social and road networks must be selected."
                )
                return
        
        # Determine which mode is active and get keywords accordingly
        if hasattr(self.__windows[9], 'userModeRadio') and self.__windows[9].userModeRadio.isChecked():
            # User mode - get keywords from selected user
            if self.queryUser is None:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Query User Required",
                    "Please select a query user or switch to direct keyword input mode."
                )
                return
                
            query_keywords = self.selectedSocialNetwork.getUserKeywords(self.queryUser[0])
            if not query_keywords:
                QtWidgets.QMessageBox.warning(
                    self,
                    "No Keywords Found",
                    "The selected query user has no keywords."
                )
                return
        else:
            # Keyword mode - get keywords from text input
            keyword_text = self.__windows[9].keywordInput.toPlainText().strip()
            if not keyword_text:
                QtWidgets.QMessageBox.warning(
                    self,
                    "No Keywords Entered",
                    "Please enter at least one keyword."
                )
                return
                
            # Parse keywords and convert to keyword IDs
            keyword_names = [k.strip() for k in keyword_text.split(',') if k.strip()]
            query_keywords = []
            invalid_keywords = []
            
            # Convert keyword names to IDs using the reverse map
            for keyword in keyword_names:
                keyword_id = None
                # Try to find the keyword in the reverse map
                for k_id, k_name in self.selectedSocialNetwork._SocialNetwork__keywordMap.items():
                    if k_name.lower() == keyword.lower():
                        keyword_id = k_id
                        break
                
                if keyword_id:
                    query_keywords.append(keyword_id)
                else:
                    invalid_keywords.append(keyword)
            
            # Check if we have any valid keywords
            if not query_keywords:
                if invalid_keywords:
                    QtWidgets.QMessageBox.warning(
                        self,
                        "Invalid Keywords",
                        f"None of the entered keywords were found in the system. Invalid keywords: {', '.join(invalid_keywords)}"
                    )
                else:
                    QtWidgets.QMessageBox.warning(
                        self,
                        "No Keywords Entered",
                        "Please enter at least one keyword."
                    )
                return
            
            # Warn about invalid keywords but continue with valid ones
            if invalid_keywords:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Some Invalid Keywords",
                    f"The following keywords were not found and will be ignored: {', '.join(invalid_keywords)}"
                )
        
        # Get parameters
        top_k = self.__windows[9].topKInput.value()
        radius = int(self.__windows[9].radiusCombo.currentText())
        min_similarity = self.__windows[9].minSimInput.value()
        use_tree_optimization = self.__windows[9].treeOptCheck.isChecked()
        
        # Always use precomputation if available
        use_precomputation = True
        
        # Get scoring weights
        keyword_weight = self.__windows[9].keywordWeightSlider.value() / 100
        distance_weight = self.__windows[9].distanceWeightSlider.value() / 100
        connection_weight = self.__windows[9].connectionWeightSlider.value() / 100
        
        # Normalize weights
        total = keyword_weight + distance_weight + connection_weight
        if total > 0:
            keyword_weight = keyword_weight / total
            distance_weight = distance_weight / total
            connection_weight = connection_weight / total
        
        # Update community detector with new weights
        self.communityDetector.scorer = CommunityScorer(
            keyword_weight=keyword_weight,
            distance_weight=distance_weight,
            connection_weight=connection_weight
        )
        
        # Store the current weights for visualization
        self.current_scoring_weights = {
            'keyword': keyword_weight,
            'distance': distance_weight,
            'connection': connection_weight
        }
        
        # Update status
        self.__windows[9].statusLabel.setText("Finding communities...")
        self.__windows[9].searchBtn.setEnabled(False)
        self.__windows[9].repaint()  # Force UI update
        
        try:
            # Start timing
            self.CTstart = time.time()
            
            # Find communities
            communities = self.communityDetector.find_top_k_communities(
                query_keywords,
                k=top_k,
                radius=radius,
                min_similarity=min_similarity,
                use_precomputation=use_precomputation,
                use_tree_optimization=use_tree_optimization
            )
            
            # End timing
            self.CTend = time.time()
            self.__UpdateQueryTime()
            
            # Update status
            if communities:
                self.__windows[9].statusLabel.setText(f"Found {len(communities)} communities.")
                
                # Store communities for later use
                self.current_communities = communities
                
                # Visualize communities
                self.visualizeCommunities(communities)
                
                # Visualize social network with the found communities
                self.visualize_social_network(communities)
                
                # Close dialog
                self.__windows[9].accept()
            else:
                self.__windows[9].statusLabel.setText("No communities found matching criteria.")
        
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.__windows[9].statusLabel.setText(f"Error: {str(e)}")
        
        # Re-enable search button
        self.__windows[9].searchBtn.setEnabled(True)

    def visualizeCommunities(self, communities):
        """Visualize communities on the map and in the social network view"""
        if not communities:
            return
        
        # Clear previous visualization
        self.clearView()
        
        # Create plots
        self.createSumPlot("Community Detection")
        
        # Visualize road network if available
        if self.selectedRoadNetwork:
            self.selectedRoadNetwork.visualize(self.roadGraphWidget)
        
        # Use different colors for different communities
        community_colors = [
            (50, 50, 200),   # Blue
            (200, 50, 50),   # Red
            (50, 200, 50),   # Green
            (200, 200, 50),  # Yellow
            (200, 50, 200),  # Purple
            (50, 200, 200),  # Cyan
            (150, 100, 50),  # Brown
            (100, 150, 50),  # Olive
            (50, 100, 150),  # Steel Blue
            (150, 50, 100),  # Dark Pink
        ]
        
        # Visualize all communities on the map with different colors
        for i, community in enumerate(communities):
            color_idx = i % len(community_colors)
            color = community_colors[color_idx]
            
            # Plot regular community members
            x = []
            y = []
            for user in community['users']:
                try:
                    user_location = self.selectedSocialNetwork.userLoc(user)
                    x.append(float(user_location[0][0]))
                    y.append(float(user_location[0][1]))
                except:
                    continue
            
            if x and y:
                # Plot regular members as circles
                self.roadGraphWidget.plot(x, y, pen=None, symbol='o', symbolSize=10,
                                    symbolPen=(*color, 100), 
                                    symbolBrush=(*color, 175))
                
                # Plot center user as a star if it exists
                if 'center' in community:
                    try:
                        center_loc = self.selectedSocialNetwork.userLoc(community['center'])
                        self.roadGraphWidget.plot([float(center_loc[0][0])], [float(center_loc[0][1])],
                                            pen=None, symbol='star', symbolSize=30,
                                            symbolPen=(*color, 255),
                                            symbolBrush=(*color, 255))
                    except:
                        pass
        
        # Create network graph for visualization of top community
        top_community = communities[0]
        network = nx.Graph()
        
        # Create a more detailed network visualization with all communities
        for i, community in enumerate(communities):
            color = 'green' if i == 0 else f'rgb({50+i*30}, {50+i*20}, {150+i*10})'
            shape = 'star' if i == 0 else 'dot'
            
            # Add center node with larger size and star shape
            network.add_node(
                community['center'], 
                physics=True, 
                label=f"Center {i+1}: {community['center']}", 
                color=color, 
                size=25, 
                shape='star',
                group=i,
                title=f"Community {i+1} Center<br>Score: {community['score']:.4f}"
            )
            
            # Add all community members
            for user in community['users']:
                if user != community['center']:
                    # Check if node already exists (might be in multiple communities)
                    if user in network.nodes:
                        # Add information about being in multiple communities
                        title = network.nodes[user].get('title', '')
                        title += f"<br>Also in Community {i+1}"
                        network.nodes[user]['title'] = title
                        # Don't change the node appearance if already in the network
                    else:
                        network.add_node(
                            user, 
                            physics=True, 
                            label=str(user), 
                            color=color, 
                            size=15,
                            group=i,
                            title=f"Member of Community {i+1}"
                        )
            
            # Add connections within community
            for user in community['users']:
                # Get user's relationships
                try:
                    rels = self.selectedSocialNetwork.getUserRel(user)
                    rel_users = []
                    for r in rels:
                        if r and r[0]:
                            rel_users.append(r[0])
                
                    # Find relationships within the community
                    relations = set(rel_users) & set(community['users'])
                    for r in relations:
                        if not network.has_edge(user, r):
                            network.add_edge(user, r, color=color, group=i, 
                                            title=f"Connection in Community {i+1}")
                except Exception as e:
                    print(f"Error processing relations for user {user}: {str(e)}")
        
        # --------- Direct HTML visualization approach ---------
        # Create basic HTML with a clear container for vis.js network
        basic_html = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Community Network</title>
            <style>
                html, body {
                    width: 100%;
                    height: 100%;
                    margin: 0;
                    padding: 0;
                    overflow: hidden;
                    background-color: white;
                }
                #mynetwork {
                    width: 100%;
                    height: 100%;
                    border: none;
                    background-color: white;
                }
            </style>
            <!-- Vis.js library -->
            <script type="text/javascript" src="https://cdnjs.cloudflare.com/ajax/libs/vis/4.21.0/vis.min.js"></script>
            <link href="https://cdnjs.cloudflare.com/ajax/libs/vis/4.21.0/vis.min.css" rel="stylesheet" type="text/css" />
            <style>
                .network-title {
                    position: absolute;
                    top: 10px;
                    left: 10px;
                    z-index: 10;
                    background-color: rgba(255, 255, 255, 0.8);
                    padding: 5px 10px;
                    border-radius: 5px;
                    font-family: Arial, sans-serif;
                    font-size: 14px;
                    font-weight: bold;
                    color: #333;
                    box-shadow: 0 1px 4px rgba(0,0,0,0.2);
                }
            </style>
        </head>
        <body>
            <div class="network-title">Social Network Community Detection</div>
            <div id="mynetwork"></div>
            <script type="text/javascript">
                // The network data will be inserted here
                var nodes = new vis.DataSet(NODES_DATA);
                var edges = new vis.DataSet(EDGES_DATA);
                
                // Create a network
                var container = document.getElementById('mynetwork');
                var data = {
                    nodes: nodes,
                    edges: edges
                };
                var options = OPTIONS_DATA;
                var network = new vis.Network(container, data, options);
            </script>
        </body>
        </html>
        """
        
        # Get nodes and edges data as JSON
        nodes_data = []
        edges_data = []
        
        for n, attrs in network.nodes(data=True):
            node_data = {
                'id': str(n),
                'label': attrs.get('label', str(n)),
                'color': attrs.get('color', '#97c2fc'),
                'size': attrs.get('size', 10),
                'shape': attrs.get('shape', 'dot'),
                'title': attrs.get('title', ''),
                'group': attrs.get('group', 0)
            }
            nodes_data.append(node_data)
        
        for u, v, attrs in network.edges(data=True):
            edge_data = {
                'from': str(u),
                'to': str(v),
                'title': attrs.get('title', ''),
                'color': attrs.get('color', '#848484')
            }
            edges_data.append(edge_data)
        
        # Physics options optimized for communities
        options_data = {
            "nodes": {
                "font": {"size": 12, "face": "Arial", "color": "black"},
                "scaling": {"min": 10, "max": 30},
                "shadow": {"enabled": True}
            },
            "edges": {
                "color": {"inherit": "from"},
                "smooth": {"type": "continuous", "forceDirection": "none"},
                "width": 2,
                "shadow": {"enabled": True}
            },
            "physics": {
                "barnesHut": {
                    "gravitationalConstant": -2000,
                    "centralGravity": 0.3,
                    "springLength": 120,
                    "springConstant": 0.05,
                    "damping": 0.09,
                    "avoidOverlap": 0.5
                },
                "stabilization": {
                    "enabled": True,
                    "iterations": 1500,
                    "updateInterval": 25,
                    "fit": True
                },
                "solver": "barnesHut",
                "enabled": True
            },
            "interaction": {
                "navigationButtons": True,
                "keyboard": True,
                "hover": True,
                "multiselect": True,
                "dragNodes": True
            },
            "layout": {
                "improvedLayout": True,
                "hierarchical": {
                    "enabled": False
                }
            }
        }
        
        # Replace placeholders in the HTML template
        import json
        html_content = basic_html
        html_content = html_content.replace('NODES_DATA', json.dumps(nodes_data))
        html_content = html_content.replace('EDGES_DATA', json.dumps(edges_data))
        html_content = html_content.replace('OPTIONS_DATA', json.dumps(options_data))
        
        # Write to a file
        with open('direct-network-viz.html', 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        # Create a completely new QWebEngineView
        self.socialNetWidget = QWebEngineView()
        self.socialNetWidget.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.socialNetWidget.setMinimumWidth(400)
        self.socialNetWidget.setMinimumHeight(400)
        
        # Load the HTML file directly
        try:
            self.socialNetWidget.load(QtCore.QUrl.fromLocalFile(os.path.abspath('direct-network-viz.html')))
        except Exception as e:
            print(f"Error loading network visualization: {str(e)}")
            # Show error message in web view
            error_html = f"""
            <html>
            <body style="margin:20px;font-family:Arial,sans-serif;background:#f8f8f8;">
                <div style="text-align:center;margin-top:50px;">
                    <h2 style="color:#e74c3c;">Network visualization could not be loaded</h2>
                    <p>Error: {str(e)}</p>
                    <p>Check console for details.</p>
                </div>
            </body>
            </html>
            """
            self.socialNetWidget.setHtml(error_html)
        
        # Create a completely new widget hierarchy
        new_view = QtWidgets.QWidget()
        main_layout = QtWidgets.QHBoxLayout()
        main_layout.setContentsMargins(1, 1, 1, 1)
        main_layout.setSpacing(1)
        new_view.setLayout(main_layout)
        
        # Left panel (community list) - Made wider
        left_panel = QtWidgets.QWidget()
        left_panel.setMinimumWidth(350)  # Increased from 250
        left_panel.setMaximumWidth(400)  # Increased from 300
        left_panel.setStyleSheet("background-color: #2D2D2D; color: white;")
        left_layout = QtWidgets.QVBoxLayout()
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        left_panel.setLayout(left_layout)
        
        # Add title to the left panel
        title_label = QtWidgets.QLabel("Ranked Communities")
        title_label.setStyleSheet("font-size: 16pt; font-weight: bold; padding: 10px; border-bottom: 1px solid #444;")
        title_label.setAlignment(QtCore.Qt.AlignCenter)
        left_layout.addWidget(title_label)
        
        # Create ranked communities table for left panel
        communities_table = QtWidgets.QTableWidget()
        communities_table.setRowCount(len(communities))
        communities_table.setColumnCount(4)
        communities_table.setHorizontalHeaderLabels(["Center", "Size", "Score", "View"])
        communities_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        communities_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        communities_table.verticalHeader().setVisible(False)
        communities_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        communities_table.setShowGrid(True)
        communities_table.setStyleSheet("""
            QTableWidget {
                background-color: #2D2D2D;
                color: white;
                border: none;
            }
            QTableWidget::item { 
                padding: 5px;
                border-bottom: 1px solid #444;
            }
            QHeaderView::section {
                background-color: #2D2D2D;
                color: white;
                padding: 5px;
                border: none;
                border-bottom: 1px solid #444;
                font-weight: bold;
            }
        """)
        
        # Populate communities table
        for i, community in enumerate(communities):
            # Center user
            center_item = QtWidgets.QTableWidgetItem(str(community['center']))
            center_item.setTextAlignment(QtCore.Qt.AlignCenter)
            communities_table.setItem(i, 0, center_item)
        
            # Size
            size_item = QtWidgets.QTableWidgetItem(str(community['size']))
            size_item.setTextAlignment(QtCore.Qt.AlignCenter)
            communities_table.setItem(i, 1, size_item)
        
            # Score
            score_item = QtWidgets.QTableWidgetItem(f"{community['score']:.4f}")
            score_item.setTextAlignment(QtCore.Qt.AlignCenter)
            communities_table.setItem(i, 2, score_item)
        
            # View button
            view_button = QtWidgets.QPushButton("View")
            view_button.setStyleSheet("background-color: #4CAF50; color: white;")
            view_button.clicked.connect(lambda checked, idx=i: self.viewCommunity(idx))
            communities_table.setCellWidget(i, 3, view_button)
        
        communities_table.resizeColumnsToContents()
        
        # Add table to the left panel (set to expand vertically to fill all space)
        left_layout.addWidget(communities_table, 1)  # 1 means stretch factor, makes it expand to fill space
        
        # Right section (contains map, social network, and score)
        right_panel = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout()
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_panel.setLayout(right_layout)
        
        # Create a custom toolbar widget and add it to the top of the view
        toolbar_widget = QtWidgets.QWidget()
        toolbar_layout = QtWidgets.QHBoxLayout()
        toolbar_layout.setContentsMargins(2, 2, 2, 2)
        toolbar_widget.setLayout(toolbar_layout)
        
        # Add back button
        back_btn = QtWidgets.QPushButton("Back")
        back_btn.clicked.connect(self.viewSummary)
        toolbar_layout.addWidget(back_btn)
        
        # Add some spacing
        toolbar_layout.addStretch()
        
        # Add the toolbar to the top of the right panel
        right_layout.addWidget(toolbar_widget)
        
        # Create a widget for the visualizations
        viz_widget = QtWidgets.QWidget()
        viz_layout = QtWidgets.QHBoxLayout()
        viz_layout.setContentsMargins(0, 0, 0, 0)
        viz_layout.setSpacing(0)
        viz_widget.setLayout(viz_layout)
        
        # Create a frame for the social network visualization to ensure proper display
        social_frame = QtWidgets.QFrame()
        social_frame.setFrameShape(QtWidgets.QFrame.StyledPanel)
        social_frame.setLineWidth(1)
        social_frame.setMinimumWidth(400)
        social_layout = QtWidgets.QVBoxLayout()
        social_layout.setContentsMargins(0, 0, 0, 0)
        social_frame.setLayout(social_layout)
        
        # Add the WebEngineView to show the social network
        social_layout.addWidget(self.socialNetWidget)
        
        # Add social network visualization to the left side
        viz_layout.addWidget(social_frame, 1)
        
        # Add road map to the right side
        viz_layout.addWidget(self.win, 1)
        
        # Add the visualization widget to the right panel
        right_layout.addWidget(viz_widget, 3)  # Top section takes 3/4 of height
        
        # Add score information
        score_widget = QtWidgets.QWidget()
        score_widget.setStyleSheet("background-color: #2D2D2D; color: white;")
        score_layout = QtWidgets.QVBoxLayout()
        score_layout.setContentsMargins(10, 10, 10, 10)
        score_widget.setLayout(score_layout)
        
        # Title
        score_title = QtWidgets.QLabel("Community Score")
        score_title.setStyleSheet("font-size: 16pt; font-weight: bold;")
        score_title.setAlignment(QtCore.Qt.AlignCenter)
        score_layout.addWidget(score_title)
        
        # Overall score
        overall = QtWidgets.QLabel(f"Overall Score: {top_community['score']:.4f}")
        overall.setStyleSheet("font-size: 14pt;")
        overall.setAlignment(QtCore.Qt.AlignCenter)
        score_layout.addWidget(overall)
        
        # Component scores - with explicit labels and progress bars and updated weights
        components = top_community['components']
        
        # Default weights if not set
        if not hasattr(self, 'current_scoring_weights'):
            self.current_scoring_weights = {
                'keyword': 0.4,
                'distance': 0.3,
                'connection': 0.3
            }
        
        # Keywords score with updated weight percentage
        keywords_layout = QtWidgets.QHBoxLayout()
        keywords_label = QtWidgets.QLabel(f"Keywords ({self.current_scoring_weights['keyword']*100:.0f}%):")
        keywords_label.setMinimumWidth(150)  # Wider to accommodate percentage
        keywords_layout.addWidget(keywords_label)
        
        keywords_bar = QtWidgets.QProgressBar()
        keywords_bar.setObjectName("keywords_bar")
        keywords_bar.setRange(0, 100)
        keywords_bar.setValue(int(components['keywords'] * 100))
        keywords_bar.setFormat(f"{components['keywords']*100:.1f}%")
        keywords_bar.setStyleSheet("QProgressBar { text-align: center; background-color: #444; border: none; color: white; } QProgressBar::chunk { background-color: #3498db; }")
        keywords_layout.addWidget(keywords_bar)
        score_layout.addLayout(keywords_layout)
        
        # Distance score with updated weight percentage
        distance_layout = QtWidgets.QHBoxLayout()
        distance_label = QtWidgets.QLabel(f"Distance ({self.current_scoring_weights['distance']*100:.0f}%):")
        distance_label.setMinimumWidth(150)  # Wider to accommodate percentage
        distance_layout.addWidget(distance_label)
        
        distance_bar = QtWidgets.QProgressBar()
        distance_bar.setObjectName("distance_bar")
        distance_bar.setRange(0, 100)
        distance_bar.setValue(int(components['distance'] * 100))
        distance_bar.setFormat(f"{components['distance']*100:.1f}%")
        distance_bar.setStyleSheet("QProgressBar { text-align: center; background-color: #444; border: none; color: white; } QProgressBar::chunk { background-color: #3498db; }")
        distance_layout.addWidget(distance_bar)
        score_layout.addLayout(distance_layout)
        
        # Connections score with updated weight percentage
        connections_layout = QtWidgets.QHBoxLayout()
        connections_label = QtWidgets.QLabel(f"Connections ({self.current_scoring_weights['connection']*100:.0f}%):")
        connections_label.setMinimumWidth(150)  # Wider to accommodate percentage
        connections_layout.addWidget(connections_label)
        
        connections_bar = QtWidgets.QProgressBar()
        connections_bar.setObjectName("connections_bar")
        connections_bar.setRange(0, 100)
        connections_bar.setValue(int(components['connections'] * 100))
        connections_bar.setFormat(f"{components['connections']*100:.1f}%")
        connections_bar.setStyleSheet("QProgressBar { text-align: center; background-color: #444; border: none; color: white; } QProgressBar::chunk { background-color: #3498db; }")
        connections_layout.addWidget(connections_bar)
        score_layout.addLayout(connections_layout)
        
        # Community stats
        stats = QtWidgets.QLabel(f"Size: {top_community['size']} users\nCenter: {top_community['center']}")
        stats.setAlignment(QtCore.Qt.AlignCenter)
        score_layout.addWidget(stats)
        
        # Add score widget to right layout
        right_layout.addWidget(score_widget, 1)  # Bottom section takes 1/4 of height
        
        # Add panels to main layout
        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_panel, 1)  # Give right section priority to expand
        
        # Set central widget
        self.setCentralWidget(new_view)
        
        # Save reference to the view
        self.view = new_view
        
        # Hide timeline
        self.timeline.hide()

    def viewCommunity(self, community_idx):
        """Switch visualization to show the selected community"""
        if not self.current_communities or community_idx >= len(self.current_communities):
            return

        # Get the selected community
        community = self.current_communities[community_idx]

        # Create network graph for visualization
        network = nx.Graph()

        # Add center node
        network.add_node(
            community['center'], 
            physics=True, 
            label=f"Center: {community['center']}", 
            color='green', 
            size=25, 
            shape='star'
        )

        # Add community members
        for user in community['users']:
            if user != community['center']:
                network.add_node(user, physics=True, label=str(user), color='blue', size=15)

        # Add connections
        for user in community['users']:
            try:
                rels = self.selectedSocialNetwork.getUserRel(user)
                rel_users = []
                for r in rels:
                    if r:
                        rel_users.append(r[0])
            
                relations = set(rel_users) & set(community['users'])
                for r in relations:
                    network.add_edge(user, r, color='black')
            except:
                continue

        # Direct HTML visualization approach
        # Create basic HTML with a clear container for vis.js network
        basic_html = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Community Network</title>
            <style>
                html, body {
                    width: 100%;
                    height: 100%;
                    margin: 0;
                    padding: 0;
                    overflow: hidden;
                    background-color: white;
                }
                #mynetwork {
                    width: 100%;
                    height: 100%;
                    border: none;
                    background-color: white;
                }
                .network-title {
                    position: absolute;
                    top: 5px;
                    left: 0;
                    right: 0;
                    text-align: center;
                    z-index: 10;
                    font-family: Arial, sans-serif;
                    font-size: 12px;
                    font-weight: normal;
                    color: #000;
                }
            </style>
            <!-- Vis.js library -->
            <script type="text/javascript" src="https://cdnjs.cloudflare.com/ajax/libs/vis/4.21.0/vis.min.js"></script>
            <link href="https://cdnjs.cloudflare.com/ajax/libs/vis/4.21.0/vis.min.css" rel="stylesheet" type="text/css" />
        </head>
        <body>
            <div class="network-title">Social Network Community Detection</div>
            <div id="mynetwork"></div>
            <script type="text/javascript">
                // The network data will be inserted here
                var nodes = new vis.DataSet(NODES_DATA);
                var edges = new vis.DataSet(EDGES_DATA);
                
                // Create a network
                var container = document.getElementById('mynetwork');
                var data = {
                    nodes: nodes,
                    edges: edges
                };
                var options = OPTIONS_DATA;
                var network = new vis.Network(container, data, options);
            </script>
        </body>
        </html>
        """
        
        # Get nodes and edges data as JSON
        nodes_data = []
        edges_data = []
        
        for n, attrs in network.nodes(data=True):
            node_data = {
                'id': str(n),
                'label': attrs.get('label', str(n)),
                'color': attrs.get('color', '#97c2fc'),
                'size': attrs.get('size', 10),
                'shape': attrs.get('shape', 'dot'),
                'title': attrs.get('title', '')
            }
            nodes_data.append(node_data)
        
        for u, v, attrs in network.edges(data=True):
            edge_data = {
                'from': str(u),
                'to': str(v),
                'title': attrs.get('title', ''),
                'color': attrs.get('color', '#848484')
            }
            edges_data.append(edge_data)
        
        # Physics options optimized for communities
        options_data = {
            "nodes": {
                "font": {"size": 12, "face": "Arial", "color": "black"},
                "scaling": {"min": 10, "max": 30}
            },
            "edges": {
                "color": {"inherit": False},
                "smooth": {"type": "continuous", "forceDirection": "none"}
            },
            "physics": {
                "barnesHut": {
                    "gravitationalConstant": -2000,
                    "centralGravity": 0.3,
                    "springLength": 95,
                    "springConstant": 0.04,
                    "avoidOverlap": 0.5
                },
                "stabilization": {
                    "enabled": True,
                    "iterations": 1000,
                    "fit": True
                },
                "minVelocity": 0.75
            },
            "interaction": {
                "navigationButtons": True,
                "keyboard": True,
                "dragNodes": True
            }
        }
        
        # Replace placeholders in the HTML template
        import json
        html_content = basic_html
        html_content = html_content.replace('NODES_DATA', json.dumps(nodes_data))
        html_content = html_content.replace('EDGES_DATA', json.dumps(edges_data))
        html_content = html_content.replace('OPTIONS_DATA', json.dumps(options_data))
        
        # Write to a file
        with open('direct-community-view.html', 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        # Load the HTML file directly
        try:
            self.socialNetWidget.load(QtCore.QUrl.fromLocalFile(os.path.abspath('direct-community-view.html')))
        except Exception as e:
            print(f"Error updating network visualization: {str(e)}")
            # Show error message in web view
            error_html = f"""
            <html>
            <body style="margin:20px;font-family:Arial,sans-serif;background:#f8f8f8;">
                <div style="text-align:center;margin-top:50px;">
                    <h2 style="color:#e74c3c;">Network visualization could not be loaded</h2>
                    <p>Error: {str(e)}</p>
                </div>
            </body>
            </html>
            """
            self.socialNetWidget.setHtml(error_html)

        # Find score widget and update labels with current weights
        for widget in self.findChildren(QtWidgets.QLabel):
            if widget.text().startswith("Overall Score:"):
                widget.setText(f"Overall Score: {community['score']:.4f}")
            elif widget.text().startswith("Size:"):
                widget.setText(f"Size: {community['size']} users\nCenter: {community['center']}")
            elif widget.text().startswith("Keywords ("):
                widget.setText(f"Keywords ({self.current_scoring_weights['keyword']*100:.0f}%):")
            elif widget.text().startswith("Distance ("):
                widget.setText(f"Distance ({self.current_scoring_weights['distance']*100:.0f}%):")
            elif widget.text().startswith("Connections ("):
                widget.setText(f"Connections ({self.current_scoring_weights['connection']*100:.0f}%):")

        # Update progress bars
        keywords_bar = self.findChild(QtWidgets.QProgressBar, "keywords_bar")
        if keywords_bar:
            keywords_bar.setValue(int(community['components']['keywords'] * 100))
            keywords_bar.setFormat(f"{community['components']['keywords']*100:.1f}%")
        
        distance_bar = self.findChild(QtWidgets.QProgressBar, "distance_bar")
        if distance_bar:
            distance_bar.setValue(int(community['components']['distance'] * 100))
            distance_bar.setFormat(f"{community['components']['distance']*100:.1f}%")
        
        connections_bar = self.findChild(QtWidgets.QProgressBar, "connections_bar")
        if connections_bar:
            connections_bar.setValue(int(community['components']['connections'] * 100))
            connections_bar.setFormat(f"{community['components']['connections']*100:.1f}%")

    def __keywordCommunity(self):
        self.queryInput.community()

    def __keywordTimeCommunity(self):
        self.queryInput.communityTime()

    def __queryInput(self):
        self.queryInput.kdQuery()

    def __menuBar(self):
        menu = MenuBar(self.menuBar())

        menu.addMenu("File")
        menu.addChild("Files", "File", shortcut="Ctrl+f", tooltip="View files", action=self.viewFiles)

        menu.addMenu("View")
        menu.createGroup("ViewGroup", self)
        menu.addChild("Summary View", "View", group="ViewGroup", tooltip="View summary graphs", action=self.viewSummary)
        menu.addChild("Full View", "View", group="ViewGroup", tooltip="View full graphs", action=self.viewSummary,
                      checked=True)

        networks = self.getCompleteNetworks()
        sNetworks = networks["Social Networks"]
        rNetworks = networks["Road Networks"]

        menu.addMenu("Social Networks")
        menu.createGroup("SocialNetworkGroup", self)
        menu.addChild("None", "Social Networks", group="SocialNetworkGroup", tooltip="Display no social network",
                      action=lambda j: self.displaySocialNetwork(None), checked=True)
        for x in sNetworks:
            menu.addChild(x, "Social Networks", group="SocialNetworkGroup",
                          tooltip=f"Switch to view social network {x}",
                          action=lambda j, a=x: self.displaySocialNetwork(a))

        menu.addMenu("Road Networks")
        menu.createGroup("RoadNetworkGroup", self)
        menu.addChild("None", "Road Networks", group="RoadNetworkGroup", tooltip="Display no road network",
                      action=lambda j: self.displayRoadNetwork(None), checked=True)
        for x in rNetworks:
            menu.addChild(x, "Road Networks", group="RoadNetworkGroup",
                          tooltip=f"Switch to view road network {x}",
                          action=lambda j, a=x: self.displayRoadNetwork(a))
            
        # Add menu for stats
        menu.addMenu("Statistics")
        menu.addChild("View", "Statistics", tooltip="View statistics", action=self.ShowStatsWindow)


        menu.addMenu("Query")
        menu.addChild("kd-truss", "Query", tooltip="kd-truss menu", action=self.__queryInput)
        menu.addChild("Community Search", "Query", tooltip="community search menu", action=self.__keywordCommunity)
        menu.addChild("Community Search w/ Time", "Query", tooltip="community search w/ time menu", action=self.__keywordTimeCommunity)
        menu.addChild("BitVector Community Search", "Query", tooltip="optimized community search", action=self.__bitvectorCommunitySearch)

    def clearView(self):
        self.win.removeItem(self.roadGraphWidget)
        if self.socialGraphWidget:
            self.win.removeItem(self.socialGraphWidget)
        if self.queryUserPlots:
            self.queryUserPlots = []
        self.roadGraphWidget = None
        self.socialGraphWidget = None
        self.timeline.hide()

    def dijkstra(self, queryUser):
        '''if self.selectedRoadNetwork is not None:
            visited = []
            numOfV = self.selectedRoadNetwork.nodeCount()
            D = {v: float('inf') for v in range(numOfV)}
            startVertex = self.selectedRoadNetwork.closestNode(queryUser[1][0][0], queryUser[1][0][1])
            D[startVertex] = 0
            pq = PriorityQueue()
            pq.put((0, startVertex))
            while not pq.empty():
                (dist, current_vertex) = pq.get()
                visited.append(current_vertex)
                for neighbor in range(current_vertex - 200, current_vertex + 200):
                    edge = self.selectedRoadNetwork.isAnEdge(str(float(current_vertex)), str(float(neighbor)))
                    if edge is not None:
                        distance = self.selectedRoadNetwork.getEdgeDistance(str(edge))
                        if neighbor not in visited:
                            old_cost = D[neighbor]
                            new_cost = D[current_vertex] + float(distance)
                            if new_cost < old_cost:
                                pq.put((new_cost, neighbor))
                                D[neighbor] = new_cost
            print(D)'''

    # Handles summary view
    def viewSummary(self):
        # Switch view to summary
        if not self.summarySelected:
            self.summarySelected = True
            self.clearView()
            # Displays summary plots
            self.createSumPlot("Summary")
            self.socialNetWidget = QWebEngineView()
            with open('nx.html', 'r') as f:
                html = f.read()
                self.socialNetWidget.setHtml(html)
            # Setup summary view
            self.view = QtWidgets.QWidget()
            self.sumLayout = QtWidgets.QGridLayout()
            
            self.sumLayout.setSpacing(0)
            self.sumLayout.addWidget(self.socialNetWidget, 0, 0, 2,1)
            self.sumLayout.addWidget(self.win, 0, 1)
            self.sumLayout.setColumnStretch(0, 1)
            self.sumLayout.setColumnStretch(1, 1)
            self.toolbar.navToolbar()
            self.view.setLayout(self.sumLayout)
            self.setCentralWidget(self.view)
            self.toolbar.clusterInput()
            #self.__queryInput()
            self.updateSummaryGraph()
            self.timeline.hide()

        # Switch view to main
        else:
            self.summarySelected = False
            # Setup default view
            self.view = QtWidgets.QWidget()
            self.layout = QtWidgets.QGridLayout()
            self.layout.setSpacing(0)
            self.layout.addWidget(self.win, 0, 0, 1, 2)
            # Add graph toolbars
            self.toolbar.navToolbar()
            self.view.setLayout(self.layout)
            self.setCentralWidget(self.view)
            self.toolbar.clusterInput.close()
            self.clearView()
            #self.queryInput.close()
            self.createPlots()
            # Re-visualize selected networks
            if self.selectedRoadNetwork is not None:
                self.selectedRoadNetwork.visualize(self.roadGraphWidget)
            if self.selectedSocialNetwork is not None:
                self.selectedSocialNetwork.visualize(self.socialGraphWidget, self.roadGraphWidget)
            self.plotQueryUser()
            self.timeline.hide()

    def visualizeSummaryData(self, ids, centers, sizes, relations, popSize):
     
        # Note: For some reason, the alpha value is from 0-255 not 0-100
        self.roadGraphWidget.plot(centers[:, 0], centers[:, 1], pen=None, symbol='o', symbolSize=sizes,
                                  symbolPen=(255, 0, 0), symbolBrush=(255, 0, 0, 125))

        # Create Interactive Graph HTML File Using pyvis
        queryCluster = -1
        if self.queryUser is not None:
            queryCluster = self.selectedSocialNetwork.getUserCluster(self.queryUser[0])
        network = nx.Graph()
        for i in range(0, len(centers)):
            if ids[i] == queryCluster:
                network.add_node(str(centers[i][0]) + str(centers[i][1]), physics=False, label=popSize[i], color='green',shape='star')
            else:
                network.add_node(str(centers[i][0]) + str(centers[i][1]), physics=False, label=popSize[i])
        for i in range(1, len(relations[0])):
            network.add_edge(str(relations[0][i]) + str(relations[1][i]),
                             str(relations[0][i - 1]) + str(relations[1][i - 1]))
        nt = Network()
        nt.from_nx(network)
        nt.set_options('{"layout": {"randomSeed":5}}')
        nt.save_graph('nx.html')
        # LEGACY SOCIAL NETWORK GRAPH
        #self.socialGraphWidget.plot(centers[:, 0], centers[:, 1], pen=None, symbol='o', symbolSize=20,
        #                            symbolPen=(255, 0, 0), symbolBrush=(255, 0, 0, 150))
        #self.socialGraphWidget.plot(relations[0], relations[1], connect='pairs', pen=(50, 50, 200, 100),
        #                            brush=(50, 50, 200, 100))

    def updateSummaryGraph(self):
        self.Qstart = time.time()
        # Clears last view
        if self.summarySelected:
            self.clearView()
        self.createSumPlot("Summary")
        self.socialNetWidget.reload()
        # If a road network is selected, display info
        if self.selectedRoadNetwork is not None:
            self.selectedRoadNetwork.visualize(self.roadGraphWidget)   
        # If social network is selected, display clusters
        if self.selectedSocialNetwork is not None:
            self.ids, self.centers, sizes, relations, popSize = self.selectedSocialNetwork.getSummaryClusters(self.toolbar.clusterInput.textBox.text())
            self.visualizeSummaryData(self.ids, self.centers, sizes, relations, popSize)
            with open('nx.html', 'r') as f:
                html = f.read()
                self.socialNetWidget.setHtml(html)
        self.plotQueryUser()
        self.Qend = time.time()
        self.__UpdateQueryTime()


    def interactiveKdVisualNodes(self, tree, graph=nx.Graph()):
        tempTitle = '<p>Number of hops: ' + str(tree["hops"]) + '</p><p>Distance: ' + str(tree["distance"]) + '</p><p>Common Keywords:</p><ol>'
        for key in tree["keywords"]:
            tempTitle += '<li>' + str(self.selectedSocialNetwork.getKeywordByID(key)) + '</li>'
        tempTitle += '</ol>'
        if tree["satisfy"] == True:
            graph.add_node(tree["user"], physics=False, label=str(tree["user"]), color='blue', size=15, title=tempTitle)
        else:
            graph.add_node(tree["user"], physics=False, label=str(tree["user"]), color='grey', size=15, title=tempTitle)
        for c in list(tree["children"]):
            self.interactiveKdVisualNodes(tree["children"][c], graph)
        return graph
    
    def interactiveCommunityVisualNodes(self, tree, graph=nx.Graph()):
        tempTitle = '<p>Number of hops: ' + str(tree["hops"]) + '</p><p>Distance: ' + str(tree["distance"]) + '</p><p>Degree of Similarity:</p>' + str(tree["deg_sim"]) + '<p>Common Keywords:</p><ol>'
        for key in tree["keywords"]:
            tempTitle += '<li>' + str(self.selectedSocialNetwork.getKeywordByID(key)) + '</li>'
        tempTitle += '</ol>'
        user_pos = self.communityUserPos[tree["user"]]
        if tree["satisfy"] == True:
            graph.add_node(tree["user"], x=user_pos["x"], y=user_pos["y"], physics=False, label=str(tree["user"]), color='blue', size=15, title=tempTitle)
        else:
            graph.add_node(tree["user"], x=user_pos["x"], y=user_pos["y"], physics=False, label=str(tree["user"]), color='grey', size=15, title=tempTitle)
        for c in list(tree["children"]):
            self.interactiveCommunityVisualNodes(tree["children"][c], graph)
        return graph
    
    def interactiveTimeVisualNodes(self, tree, previousUsers, graph=nx.Graph()):
        tempTitle = '<p>Number of hops: ' + str(tree["hops"]) + '</p><p>Distance: ' + str(tree["distance"]) + '</p><p>Degree of Similarity:</p>' + str(tree["deg_sim"]) + '<p>Common Keywords:</p><ol>'
        for key in tree["keywords"]:
            tempTitle += '<li>' + str(self.selectedSocialNetwork.getKeywordByID(key)) + '</li>'
        tempTitle += '</ol>'
        user_pos = self.communityUserPos[tree["user"]]
        if tree["satisfy"] == True:
            print(str(tree["user"]))
            if str(tree["user"]) in previousUsers:
                graph.add_node(tree["user"], x=user_pos["x"], y=user_pos["y"], physics=False, label=str(tree["user"]), color='#008cff', size=15, title=tempTitle)
            else:
                graph.add_node(tree["user"], x=user_pos["x"], y=user_pos["y"], physics=False, label=str(tree["user"]), color='blue', size=15, title=tempTitle)
        else:
            graph.add_node(tree["user"], x=user_pos["x"], y=user_pos["y"], physics=False, label=str(tree["user"]), color='grey', size=15, title=tempTitle)
        for c in list(tree["children"]):
            self.interactiveTimeVisualNodes(tree["children"][c], previousUsers, graph)
        return graph


    #def visualizeKdData(self, users, keys, hops, dists):
    def visualizeKdData(self, kdTree):
        if self.queryUser is not None:
            graph = self.interactiveKdVisualNodes(kdTree, graph=nx.Graph())
            titleTemp = '<p>Keywords:</p><ol>'
            # Add query user
            queryKeys = self.selectedSocialNetwork.getUserKeywords(self.queryUser[0])
            for key in queryKeys:
                titleTemp += '<li>' + str(self.selectedSocialNetwork.getKeywordByID(key)) + '</li>'
            titleTemp += '</ol>'
            graph.add_node(self.queryUser[0], physics=False, label=str('Query: ') + str(int(float(self.queryUser[0]))),
                                color='green', size=15, shape='star', title=titleTemp)


            result_users, pass_users = self.treeUsers(kdTree, [], [])
            all_users = set(result_users) | set(pass_users)
            for u in all_users:
                rels = self.selectedSocialNetwork.getUserRel(u)
                rel_users = []
                for r in rels:
                    rel_users.append(r[0])
                relations = set(rel_users) & set(all_users)
                for r in relations:
                    graph.add_edge(u, r, color='black')
            nt = Network()
            nt.from_nx(graph)
            nt.set_options('{"layout": {"randomSeed":2}}')
            nt.save_graph('kd-trust.html')

            qu = self.queryUser[0]
            self.clearView()
            self.createSumPlot()
            if self.selectedRoadNetwork:
                self.selectedRoadNetwork.visualize(self.roadGraphWidget)
            self.ids, self.centers, sizes, relations, popSize = self.selectedSocialNetwork.getSummaryClusters(self.toolbar.clusterInput.textBox.text())
            self.visualizeSummaryData(self.ids, self.centers, sizes, relations, popSize)
            self.setQueryUser(qu)
            

            for user in result_users:
                temp = self.selectedSocialNetwork.userLoc(user)
                self.roadGraphWidget.plot([float(temp[0][0])], [float(temp[0][1])], pen=None, symbol='o', symbolSize=20,
                                          symbolPen=(50, 50, 200, 25), symbolBrush=(50, 50, 200, 175))
                #network.add_edge(self.queryUser[0], user, color='red')
            self.plotQueryUser()
            #nt = Network('100%', '100%')
            #nt.from_nx(network)
            #nt.save_graph('nx.html')

    
    def updateKdSummaryGraph(self):
        self.timeline.hide()
        self.socialNetWidget.reload()
        # If social network is selected, display clusters
        if self.selectedSocialNetwork is not None:
            #kd, keys, hops, dists = self.getKDTrust(self.__windows[6].kTextBox.text(), self.__windows[6].dTextBox.text(),
            #                     self.__windows[6].eTextBox.text())
            #self.visualizeKdData(kd, keys, hops, dists)
            self.CTstart = time.time()
            res = self.queryInput.getKdResponse()
            kdTree = self.getKDTrust(res[0], res[1], res[2])
            self.visualizeKdData(kdTree)
            # Stop counting time for query
            self.CTend = time.time()
            self.__UpdateQueryTime()
            with open('kd-trust.html', 'r') as f:
                html = f.read()
                self.socialNetWidget.setHtml(html)

    def visualizeCommunityTimeData(self, kdTree):
        if self.queryUser is not None:
            if self.timeline.getFrame() == 0 or self.previousUsers == 1:
                self.previousUsers = []
            else:
                self.previousUsers, previousPass = self.treeUsers(self.__queryFrames[self.timeline.getFrame() - 1], [], [])
            graph = self.interactiveTimeVisualNodes(kdTree, self.previousUsers, graph=nx.Graph())
            titleTemp = '<p>Keywords:</p><ol>'
            # Add query user
            queryKeys = self.selectedSocialNetwork.getUserKeywords(self.queryUser[0])
            for key in queryKeys:
                titleTemp += '<li>' + str(self.selectedSocialNetwork.getKeywordByID(key)) + '</li>'
            titleTemp += '</ol>'
            query_pos = self.communityUserPos[self.queryUser[0]]
            graph.add_node(self.queryUser[0], x=query_pos["x"], y=query_pos["y"], physics=False, label=str('Query: ') + str(int(float(self.queryUser[0]))),
                                color='green', size=15, shape='star', title=titleTemp)


            result_users, pass_users = self.treeUsers(kdTree, [], [])
            all_users = set(result_users) | set(pass_users)
            for u in all_users:
                rels = self.selectedSocialNetwork.getUserRel(u)
                rel_users = []
                for r in rels:
                    rel_users.append(r[0])
                relations = set(rel_users) & set(all_users)
                for r in relations:
                    graph.add_edge(u, r, color='black')
            nt = Network()
            nt.from_nx(graph)
            nt.set_options('{"layout": {"randomSeed":2}}')
            nt.save_graph('community-query.html')

            qu = self.queryUser[0]
            #self.clearView()
            
            self.win.removeItem(self.roadGraphWidget)
            self.roadGraphWidget = None
            self.roadGraphWidget = self.win.addPlot(row=0, col=1, title="Community Query")
            self.roadGraphWidget.clear()

            if self.selectedRoadNetwork:
                self.selectedRoadNetwork.visualize(self.roadGraphWidget)
            #self.ids, self.centers, sizes, relations, popSize = self.selectedSocialNetwork.getSummaryClusters(self.clusterInput.textBox.text())
            #self.visualizeSummaryData(self.ids, self.centers, sizes, relations, popSize)

            
            # Plot community members
            member_x = []
            member_y = []
            center_x = []
            center_y = []
            
            # First identify community centers and members
            for user in result_users:
                user_location = self.selectedSocialNetwork.userLoc(user)
                if user in pass_users:  # Community centers
                    center_x.append(float(user_location[0][0]))
                    center_y.append(float(user_location[0][1]))
                else:  # Regular community members
                    member_x.append(float(user_location[0][0]))
                    member_y.append(float(user_location[0][1]))
            
            # Plot regular community members as circles
            if member_x:
                self.roadGraphWidget.plot(member_x, member_y, pen=None, symbol='o', symbolSize=10,
                                          symbolPen=(50, 50, 200, 100), symbolBrush=(50, 50, 200, 175))
            
            # Plot community centers as stars
            if center_x:
                self.roadGraphWidget.plot(center_x, center_y, pen=None, symbol='star', symbolSize=20,
                                          symbolPen=(200, 50, 50, 200), symbolBrush=(200, 50, 50, 175))
            #self.setQueryUser(qu)
                #network.add_edge(self.queryUser[0], user, color='red')
            #self.plotQueryUser()
            if self.queryUser is not None:
                if not self.queryUserPlots:
                    [a.clear() for a in self.queryUserPlots]
                self.queryUserPlots = []
                color = 'green'
                for loc in self.queryUser[1]:
                    self.queryUserPlots.append(self.roadGraphWidget.plot([float(loc[0])], [float(loc[1])], pen=None,
                                                                        symbol='star', symbolSize=30, symbolPen=color,
                                                                        symbolBrush=color))




    def visualizeCommunityData(self, kdTree):
        if self.queryUser is not None:

            graph = self.interactiveCommunityVisualNodes(kdTree, graph=nx.Graph())
            titleTemp = '<p>Keywords:</p><ol>'
            # Add query user
            queryKeys = self.selectedSocialNetwork.getUserKeywords(self.queryUser[0])
            for key in queryKeys:
                titleTemp += '<li>' + str(self.selectedSocialNetwork.getKeywordByID(key)) + '</li>'
            titleTemp += '</ol>'
            query_pos = self.communityUserPos[self.queryUser[0]]
            graph.add_node(self.queryUser[0], x=query_pos["x"], y=query_pos["y"], physics=False, label=str('Query: ') + str(int(float(self.queryUser[0]))),
                                color='green', size=15, shape='star', title=titleTemp)


            result_users, pass_users = self.treeUsers(kdTree, [], [])
            all_users = set(result_users) | set(pass_users)
            for u in all_users:
                rels = self.selectedSocialNetwork.getUserRel(u)
                rel_users = []
                for r in rels:
                    rel_users.append(r[0])
                relations = set(rel_users) & set(all_users)
                for r in relations:
                    graph.add_edge(u, r, color='black')
            nt = Network()
            nt.from_nx(graph)
            nt.set_options('{"layout": {"randomSeed":2}}')
            nt.save_graph('community-query.html')

            qu = self.queryUser[0]
            #self.clearView()
            
            self.win.removeItem(self.roadGraphWidget)
            self.roadGraphWidget = None
            self.roadGraphWidget = self.win.addPlot(row=0, col=1, title="Community Query")
            self.roadGraphWidget.clear()

            if self.selectedRoadNetwork:
                self.selectedRoadNetwork.visualize(self.roadGraphWidget)
            #self.ids, self.centers, sizes, relations, popSize = self.selectedSocialNetwork.getSummaryClusters(self.clusterInput.textBox.text())
            #self.visualizeSummaryData(self.ids, self.centers, sizes, relations, popSize)

            
            # Plot community members
            member_x = []
            member_y = []
            center_x = []
            center_y = []
            
            # First identify community centers and members
            for user in result_users:
                user_location = self.selectedSocialNetwork.userLoc(user)
                if user in pass_users:  # Community centers
                    center_x.append(float(user_location[0][0]))
                    center_y.append(float(user_location[0][1]))
                else:  # Regular community members
                    member_x.append(float(user_location[0][0]))
                    member_y.append(float(user_location[0][1]))
            
            # Plot regular community members as circles
            if member_x:
                self.roadGraphWidget.plot(member_x, member_y, pen=None, symbol='o', symbolSize=10,
                                          symbolPen=(50, 50, 200, 100), symbolBrush=(50, 50, 200, 175))
            
            # Plot community centers as stars
            if center_x:
                self.roadGraphWidget.plot(center_x, center_y, pen=None, symbol='star', symbolSize=20,
                                          symbolPen=(200, 50, 50, 200), symbolBrush=(200, 50, 50, 175))
            #self.setQueryUser(qu)
                #network.add_edge(self.queryUser[0], user, color='red')
            #self.plotQueryUser()
            if self.queryUser is not None:
                if not self.queryUserPlots:
                    [a.clear() for a in self.queryUserPlots]
                self.queryUserPlots = []
                color = 'green'
                for loc in self.queryUser[1]:
                    self.queryUserPlots.append(self.roadGraphWidget.plot([float(loc[0])], [float(loc[1])], pen=None,
                                                                        symbol='star', symbolSize=30, symbolPen=color,
                                                                        symbolBrush=color))


    def updateCommunitySummaryGraph(self):
        self.timeline.hide()
        self.socialNetWidget.reload()
        # If social network is selected, display clusters
        if self.selectedSocialNetwork is not None:
            queryKeywords = self.queryInput.getCommunityKeywords()
            queryKeywords += self.selectedSocialNetwork.getUserKeywords(self.queryUser[0])
            queryRelsRaw = self.selectedSocialNetwork.getUserRel(self.queryUser[0])
            queryRels = []
            for r in queryRelsRaw:
                queryRels.append(r[0])
            self.CTstart = time.time()
            #community = self.communityTree(self.queryUser[0], queryKeywords, queryRels, float(self.__windows[6].kcTextBox.text()), float(self.__windows[6].kTextBox.text()), float(self.__windows[6].rTextBox.text()), float(self.__windows[6].dTextBox.text()), float(self.__windows[6].eTextBox.text()),[], 0, 0)
            res = self.queryInput.getCommunityResponse()
            
            # Get scoring weights from BitVector dialog if available
            keyword_weight = 0.4
            distance_weight = 0.3
            connection_weight = 0.3
            
            if hasattr(self, 'bitvectorDialog') and self.__windows.get(9) is not None:
                # Get values from sliders
                keyword_weight = self.__windows[9].keywordWeightSlider.value() / 100
                distance_weight = self.__windows[9].distanceWeightSlider.value() / 100
                connection_weight = self.__windows[9].connectionWeightSlider.value() / 100
                
                # Normalize weights
                total = keyword_weight + distance_weight + connection_weight
                if total > 0:
                    keyword_weight = keyword_weight / total
                    distance_weight = distance_weight / total
                    connection_weight = connection_weight / total
            
            # Use the bridge to process with bitvector optimization
            community_tree = self.community_bridge.process_community_query(
                self.queryUser[0],
                queryKeywords,
                res[0],      # min keywords
                res[3],      # radius
                res[2],      # min similarity
                keyword_weight,
                distance_weight,
                connection_weight,
                False        # Don't use tree optimization by default
            )
            
            if not community_tree:
                # Fallback to original implementation if bridge fails
                community = self.communityTree(self.queryUser[0], queryKeywords, queryRels, float(res[0]), float(res[3]), float(res[4]), float(res[1]), float(res[2]), [], 0, 0)
                community = self.pruneTree(community)
            else:
                community = community_tree
                
            temp_users = self.treeUsers(community)
            users = list(set(temp_users[0]) | set(temp_users[1]))
            for user in users:
                self.communityUserPos[user] = {
                    "x": random.randint(0, 350),
                    "y": random.randint(0, 350)
                }
            self.visualizeCommunityData(community)
            # Stop counting time for query
            self.CTend = time.time()
            self.__UpdateQueryTime()
            with open('community-query.html', 'r') as f:
                html = f.read()
                self.socialNetWidget.setHtml(html)


    
    def timelineThread(self):
        # self.socialNetWidget.reload()
        if not self.playAnimation:
            return
        # frame = self.timeline.getFrame()+1
        for frame in range(self.timeline.getFrame()+1, 11):
            if self.playAnimation:
                self.timeline.setFrame(frame)
                QTimer.singleShot(0, self.updateTimeline)  # Start the timer in the main thread
                time.sleep(2)
            else:
                break
        self.timeline.play.setText("Play")



    def playTimeline(self):
        self.playAnimation = not self.playAnimation
        if self.playAnimation:
            self.timeline_thread = threading.Thread(target=self.timelineThread)
            self.timeline_thread.start()
        self.timeline.play.setText("Pause" if self.playAnimation else "Play")
        

    def updateTimeline(self):
        # values = self.timeline.getDates()
        # # convert from int to dates
        # start = str(datetime.date(2020, 1, 1) + datetime.timedelta(days=values[0]))
        # end = str(datetime.date(2020, 1, 1) + datetime.timedelta(days=values[1]))

        #self.socialNetWidget.reload()
        # If social network is selected, display clusters
        if self.selectedSocialNetwork is not None:
            frame = self.timeline.getFrame()
            if frame == 0:
                self.timeline.setDates("Start :" + str(self.query_dates[0].strftime('%m/%d/%Y')), "End :" + str(self.query_dates[10].strftime('%m/%d/%Y')))
            else:
                self.timeline.setDates("Start :" + str(self.query_dates[0].strftime('%m/%d/%Y')), "End :" + str(self.query_dates[frame].strftime('%m/%d/%Y')))
            self.visualizeCommunityTimeData(self.__queryFrames[frame])
            
            with open('community-query.html', 'r') as f:
                html = f.read()
                self.socialNetWidget.setHtml(html)

    def get_evenly_spaced_dates(self, start_date, end_date, num_dates):
        delta = (end_date - start_date) / (num_dates - 1)
        dates = [start_date + i * delta for i in range(num_dates)]
        return dates
        
    
    def updateCommunityTimeSummaryGraph(self):
        self.timeline.show()
        self.socialNetWidget.reload()
        # If social network is selected, display clusters
        if self.selectedSocialNetwork is not None:
            
            self.CTstart = time.time()

            res = self.queryInput.getCommunityTimeResponse()
            self.query_dates = self.get_evenly_spaced_dates(datetime.datetime.strptime(res[6], "%Y-%m-%d"), datetime.datetime.strptime(res[7], "%Y-%m-%d"), 11)

            users = []
            
            for i in range(0, len(self.query_dates)):
                if i == 0:
                    queryKeywords = self.queryInput.getCommunityKeywords()
                    
                    queryKeywords += self.selectedSocialNetwork.getUserKeywordsInTime(self.queryUser[0], res[6], res[7])
                    queryRelsRaw = self.selectedSocialNetwork.getUserRel(self.queryUser[0])
                    queryPois = self.selectedSocialNetwork.getUserPoiInTime(self.queryUser[0], res[6], res[7])
                    queryRels = []
                    for r in queryRelsRaw:
                        queryRels.append(r[0])
                    community = self.communityTimeTree(
                        self.queryUser[0], 
                        queryKeywords, 
                        queryRels, 
                        queryPois, 
                        res[6],
                        res[7],
                        float(res[0]), 
                        float(res[3]), 
                        float(res[4]),
                        float(res[5]), 
                        float(res[1]), 
                        float(res[2]), 
                        [], 
                        0,
                        0)
                    self.__queryFrames.append(self.pruneTree(community))
                    frame_users = self.treeUsers(community)
                    temp_users = list(set(frame_users[0]) | set(frame_users[1]))
                    users = list(set(users) | set(temp_users))
                else:
                    date = str(self.query_dates[i-1])
                    queryKeywords = self.queryInput.getCommunityKeywords()
                    res = self.queryInput.getCommunityTimeResponse()
                    queryKeywords += self.selectedSocialNetwork.getUserKeywordsInTime(self.queryUser[0], res[6], date)
                    queryRelsRaw = self.selectedSocialNetwork.getUserRel(self.queryUser[0])
                    queryPois = self.selectedSocialNetwork.getUserPoiInTime(self.queryUser[0], res[6], date)
                    queryRels = []
                    for r in queryRelsRaw:
                        queryRels.append(r[0])
                    community = self.communityTimeTree(
                        self.queryUser[0], 
                        queryKeywords, 
                        queryRels, 
                        queryPois, 
                        res[6],
                        date,
                        float(res[0]), 
                        float(res[3]), 
                        float(res[4]),
                        float(res[5]), 
                        float(res[1]), 
                        float(res[2]), 
                        [], 
                        0,
                        0)
                    self.__queryFrames.append(self.pruneTree(community))
                    frame_users = self.treeUsers(community)
                    temp_users = list(set(frame_users[0]) | set(frame_users[1]))
                    users = list(set(users) | set(temp_users))
            for user in users:
                self.communityUserPos[user] = {
                    "x": random.randint(0, 500),
                    "y": random.randint(0, 500)
                }
            # self.visualizeCommunityData(self.__queryFrames[0])
            # Stop counting time for query
            self.CTend = time.time()
            self.__UpdateQueryTime()
            # with open('community-query.html', 'r') as f:
            #     html = f.read()
            #     self.socialNetWidget.setHtml(html)
            self.updateTimeline()

    #Generate kdtrust from input
    def getKDTrust(self, keywords, hops, distance):
        if self.queryUser is not None:
 
            #kd = KDTrust(self.selectedRoadNetwork, self.selectedSocialNetwork, self.queryUser[0], float(keywords), float(distance), float(hops))
            queryKeywords = self.selectedSocialNetwork.getUserKeywords(self.queryUser[0])


            if float(distance) == 0.0:
                distance = 9999.0

            print(distance)

            kdTree = self.kdTree(queryKeywords, self.queryUser[0], float(keywords), float(distance), float(hops), 0, 0, [])
            kdTree = self.pruneTree(kdTree)
            """
            # Users with common keywords
            common, keys = self.usersCommonKeyword(k=float(keywords))
            # Narrow query down to users within hops
            common, hops = self.usersWithinHops(common, h=float(hops))
            # Narrow down with degree of similarity distance (longest compute time)
            common, dists = self.usersWithinDistance(common, d=float(distance))

            neighbors = []
            for user in common:
                path = self.selectedSocialNetwork.shortestPath(self.queryUser[0], user)
                print(path)
                neighbors = list(set(neighbors) | set(path))
            print(neighbors)
            
            common = []
            keys = []
            hops = []
            dists = []
            users = kd.getUsers()
            """
            return kdTree
        

    def __UpdateQueryTime(self):
        self.SummaryResponseTime = (self.Qend - self.Qstart) * 1000
        self.ClusterResponseTime = (self.CTend - self.CTstart) * 1000
        self.__ViewStats()

    # Returns query user in form [id, [[lat, lon], [lat, lon]]]
    def setQueryUser(self, user, window=4):
        if self.queryUser is not None:
            [a.clear() for a in self.queryUserPlots]
            self.queryUserPlots = []
        self.queryUser = self.selectedSocialNetwork.getUser(user)
        self.plotQueryUser()
        self.queryUserToolbar.userLabel.setText(user.split(".0")[0])
        #self.usersCommonKeyword()
        self.__windows[window].close()
        self.dijkstra(self.queryUser)

    def plotQueryUser(self):
        if self.queryUser is not None:
            if not self.queryUserPlots:
                [a.clear() for a in self.queryUserPlots]
            self.queryUserPlots = []
            color = 'green'
            for loc in self.queryUser[1]:
                if self.summarySelected:
                    self.clearView()
                    self.plottingUserRefresh()
                self.queryUserPlots.append(self.roadGraphWidget.plot([float(loc[0])], [float(loc[1])], pen=None,
                                                                     symbol='star', symbolSize=30, symbolPen=color,
                                                                     symbolBrush=color))

    def plottingUserRefresh(self):
        self.createSumPlot("Summary")
        self.socialNetWidget.reload()
        if self.selectedRoadNetwork is not None:
            self.selectedRoadNetwork.visualize(self.roadGraphWidget)
            # If social network is selected, display clusters
        if self.selectedSocialNetwork is not None:
           self.ids, self.centers, sizes, relations, popSize = self.toolbar.clusterInput.textBox.text()
           self.visualizeSummaryData(self.ids, self.centers, sizes, relations, popSize)
           with open('nx.html', 'r') as f:
                html = f.read()
                self.socialNetWidget.setHtml(html)


    def setQueryKeyword(self, keyword):
        self.queryKeyword = keyword
        self.queryUserToolbar.keywordLabel.setText(self.selectedSocialNetwork.getKeywordByID(keyword))
        self.__windows[5].close()

    # Display for loading networks
    def viewFiles(self):
        # Set up hierarchy base
        self.__fileTreeObjects = {
            '0': QtWidgets.QTreeWidgetItem(["Road Networks"]),
            '1': QtWidgets.QTreeWidgetItem(["Social Networks"])
        }
        # Set up tree widget
        self.__windows[0] = pg.TreeWidget()
        self.__windows[0].setWindowModality(QtCore.Qt.ApplicationModal)
        self.__windows[0].setDragEnabled(False)
        self.__windows[0].header().setSectionsMovable(False)
        self.__windows[0].header().setStretchLastSection(False)
        self.__windows[0].header().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self.__windows[0].setWindowTitle('Network Files')
        self.__windows[0].setColumnCount(2)
        self.__windows[0].resize(int(self.frameGeometry().width() / 3), int(self.frameGeometry().height() / 3))
        # Show TreeWidget
        self.__windows[0].show()
        # Add Road Networks and Social Networks to hierarchy
        self.__windows[0].addTopLevelItem(self.__fileTreeObjects['0'])
        self.__windows[0].addTopLevelItem(self.__fileTreeObjects['1'])
        # Add button to add a new Road Network
        nrn = QtWidgets.QPushButton("New Road Network")
        nrn.clicked.connect(lambda: self.newNetwork("road"))
        self.__windows[0].setItemWidget(self.__fileTreeObjects['0'], 1, nrn)
        # Add button to add a new Social Network
        nsn = QtWidgets.QPushButton("New Social Network")
        nsn.clicked.connect(lambda: self.newNetwork("social"))
        self.__windows[0].setItemWidget(self.__fileTreeObjects['1'], 1, nsn)
        # Adds all sub-objects to roadNetworks. Each element is given a number in order for the hierarchy. For example,
        # 1.3 is the fourth child of the second element
        i = 0
        for x in self.__roadNetworks:
            i += 1
            self.__fileTreeObjects[f"0.{i}"] = QtWidgets.QTreeWidgetItem([x])
            self.__fileTreeObjects['0'].addChild(self.__fileTreeObjects[f"0.{i}"])
            j = 0
            # Adds files
            cFile = {}
            for y in self.__roadNetworks[x]:
                j += 1
                iName = self.__roadNetworks[x][y]
                if iName != f"[{iName}]":
                    iNameArr = iName.split("/")
                    iName = iNameArr[len(iNameArr) - 1]
                self.__fileTreeObjects[f"0.{i}.{j}"] = QtWidgets.QTreeWidgetItem([iName])
                self.__fileTreeObjects[f"0.{i}"].addChild(self.__fileTreeObjects[f"0.{i}.{j}"])
                cFile[j] = QtWidgets.QPushButton("Choose File")
                cFile[j].clicked.connect(
                    lambda junk, a=i, d=j, b=x, c=y: self.chooseFile(f"0.{a}.{d}", "Road Network", b, c))
                self.__windows[0].setItemWidget(self.__fileTreeObjects[f"0.{i}.{j}"], 1, cFile[j])
        # Adds all sub-objects to socialNetworks. Each element is given a number in order for the hierarchy. For
        # example, 1.3 is the fourth child of the second element
        i = 0
        cFileS = {}
        for x in self.__socialNetworks:
            i += 1
            self.__fileTreeObjects[f"1.{i}"] = QtWidgets.QTreeWidgetItem([x])
            self.__fileTreeObjects['1'].addChild(self.__fileTreeObjects[f"1.{i}"])
            j = 0
            # Adds files
            for y in self.__socialNetworks[x]:
                j += 1
                iName = self.__socialNetworks[x][y]
                if iName != f"[{iName}]":
                    iNameArr = iName.split("/")
                    iName = iNameArr[len(iNameArr) - 1]
                self.__fileTreeObjects[f"1.{i}.{j}"] = QtWidgets.QTreeWidgetItem([iName])
                self.__fileTreeObjects[f"1.{i}"].addChild(self.__fileTreeObjects[f"1.{i}.{j}"])
                cFileS[f"{j}.{j}"] = QtWidgets.QPushButton("Choose File")
                cFileS[f"{j}.{j}"].clicked.connect(
                    lambda junk, a=i, b=j, c=x, d=y: self.chooseFile(f"1.{a}.{b}", "Social Network", c, d))
                self.__windows[0].setItemWidget(self.__fileTreeObjects[f"1.{i}.{j}"], 1, cFileS[f"{j}.{j}"])

    # TODO: Fix issue where networks aren't loaded after they are created -- program requires restart
    # Creates a new Road network
    def newNetwork(self, type):
        if type != "road" and type != "social":
            print("ERROR: newNetwork() must have type road or social")
            exit(0)
        title = ""
        network = None
        num = -1
        if type == "road":
            title = "Road Network"
            network = self.__roadNetworks
            num = 0
        elif type == "social":
            title = "Social Network"
            num = 1
            network = self.__socialNetworks
        self.__windows[1] = QtWidgets.QInputDialog()
        text, ok = self.__windows[1].getText(self, f'New {title}', f"Enter your {title.lower()} name:")
        text = str(text)
        # If the road network does not exist already, add it to the config
        if ok and text not in network.keys() and text != "":
            if type == "road":
                network[text] = {
                    "nodeFile": "[nodeFile]",
                    "edgeFile": "[edgeFile]",
                    "POIFile": "[POIFile]",
                    "keyFile": "[keyFile]",
                    "keyMapFile": "[keyMapFile]"
                }
            elif type == "social":
                network[text] = {
                    "locFile": "[locFile]",
                    "relFile": "[relFile]",
                    "keyFile": "[keyFile]",
                    "keyMapFile": "[keyMapFile]",
                    "userDataFile": "[userDataFile]",
                    "userPoiFile": "[userPoiFile]"
                }
            # Adds new road network to tree
            keys = list(network.keys())
            currItem = len(keys) + 1
            # Add new road network to hierarchy
            self.__fileTreeObjects[f"{num}.{currItem}"] = QtWidgets.QTreeWidgetItem([text])
            self.__fileTreeObjects[f'{num}'].addChild(self.__fileTreeObjects[f"{num}.{currItem}"])
            for i in range(1, len(network[text]) + 1):
                self.__fileTreeObjects[f"{num}.{currItem}.{i}"] = \
                    QtWidgets.QTreeWidgetItem([network[text]
                                               [f"{list(network[text].keys())[i - 1]}"]])
                self.__fileTreeObjects[f'{num}.{currItem}'].addChild(self.__fileTreeObjects[f"{num}.{currItem}.{i}"])
                addN = QtWidgets.QPushButton("Choose File")
                addN.clicked.connect(lambda junk, a=num, b=i, c=currItem, d=title, e=text: self.chooseFile(
                    f"{a}.{c}.{b}", f"{d}", e, f"{list(network[e].keys())[b - 1]}"))
                self.__windows[0].setItemWidget(self.__fileTreeObjects[f"{num}.{currItem}.{i}"], 1, addN)
            # Update config
            self.config.update(f"{title}s", network)

    # TODO: Implement for summary graph
    def hidePOIs(self, checked):
        if checked:
            self.clearView()
            self.createPlots()
            if self.selectedRoadNetwork is not None:
                self.selectedRoadNetwork.visualize(self.roadGraphWidget)
            if self.selectedSocialNetwork is not None:
                self.selectedSocialNetwork.visualize(self.socialGraphWidget, self.roadGraphWidget)
            #self.linkGraphAxis()
        else:
            self.clearView()
            self.createPlots()
            if self.selectedRoadNetwork is not None:
                self.selectedRoadNetwork.visualize(self.roadGraphWidget)
            self.selectedRoadNetwork.visualize(None, self.roadGraphWidget)
            if self.selectedSocialNetwork is not None:
                self.selectedSocialNetwork.visualize(self.socialGraphWidget, self.roadGraphWidget)
            #self.linkGraphAxis()

    def chooseFile(self, obj, T, network, sub):
        self.__windows[2] = QtWidgets.QFileDialog()
        pathArr = self.__windows[2].getOpenFileNames(None, f'Select {sub}', getenv('HOME'), "csv(*.csv)")[0]
        if len(pathArr) != 0:
            path = pathArr[0]
            if T == "Road Network":
                self.__roadNetworks[network][sub] = path
                self.config.update("Road Networks", self.__roadNetworks)
            elif T == "Social Network":
                self.__socialNetworks[network][sub] = path
                self.config.update("Social Networks", self.__socialNetworks)
            # Update item
            fileNameArr = path.split("/")
            fileName = fileNameArr[len(fileNameArr) - 1]
            self.__fileTreeObjects[obj].setText(0, fileName)
        self.menuBar().clear()
        self.__menuBar()

    # Return road networks that have all files and those files exist
    def getCompleteNetworks(self):
        networks = {"Social Networks": [],
                    "Road Networks": []}
        keys = self.__roadNetworks.keys()
        # Road networks
        for i in keys:
            passed = True
            for j in self.__roadNetworks[i]:
                if passed and (self.__roadNetworks[i][j] == f"[{j}]" or not exists(self.__roadNetworks[i][j])):
                    passed = False
            if passed:
                networks["Road Networks"].append(i)
        # Social networks
        keys = self.__socialNetworks.keys()
        for k in keys:
            passed = True
            for l in self.__socialNetworks[k]:
                if passed and (self.__socialNetworks[k][l] == f"[{l}]" or not exists(self.__socialNetworks[k][l])):
                    passed = False
            if passed:
                networks["Social Networks"].append(k)
        return networks

    def displayRoadNetwork(self, network):
        # If the summary is not selected
        if not self.summarySelected:
            self.clearView()
            self.selectedRoadNetwork = None
            self.createPlots()
            # Display road network
            if network is not None:
                # Visualizes the graph that is being selected
                self.__roadNetworkObjs[network].visualize(self.roadGraphWidget)
                self.selectedRoadNetwork = self.__roadNetworkObjs[network]
            # Display social network
            if self.selectedSocialNetwork is not None:
                self.selectedSocialNetwork.visualize(self.socialGraphWidget, self.roadGraphWidget)
            self.plotQueryUser()
            #self.linkGraphAxis()
        # If the summary is selected
        else:
            self.clearView()
            self.selectedRoadNetwork = None
            self.createSumPlot("Summary")
            # Display road network
            if network is not None:
                self.selectedRoadNetwork = self.__roadNetworkObjs[network]
                self.selectedRoadNetwork.visualize(self.roadGraphWidget)
            # Draw social network
            if self.selectedSocialNetwork is not None:
                self.ids, self.centers, sizes, relations, popSize = self.selectedSocialNetwork.getSummaryClusters(self.toolbar.clusterInput.textBox.text())
                self.visualizeSummaryData(self.ids, self.centers, sizes, relations, popSize)
            self.plotQueryUser()
            #self.linkGraphAxis()
        
        # Initialize community detector
        self.initializeCommunityDetector()

    def displaySocialNetwork(self, network):
        self.queryUser = None
        [a.clear() for a in self.queryUserPlots]
        self.queryUserPlots = []
        #self.queryUserToolbar.userLabel.setText("None")
        self.queryKeyword = None
        #self.queryUserToolbar.keywordLabel.setText("None")
        # If main view
        if not self.summarySelected:
            self.clearView()
            self.selectedSocialNetwork = None
            self.createPlots()
            # Re-visualizes the road network if it is selected
            if self.selectedRoadNetwork:
                self.selectedRoadNetwork.visualize(self.roadGraphWidget)
            # Visualizes social network
            if network is not None:
                self.__socialNetworkObjs[network].visualize(self.socialGraphWidget, self.roadGraphWidget)
                self.selectedSocialNetwork = self.__socialNetworkObjs[network]
            #self.linkGraphAxis()
        # If summary view
        else:
            # Removes both graphs to clear them then re-adds them
            self.clearView()
            self.createSumPlot()
            self.selectedSocialNetwork = None
            #self.createPlots("Summary")
            # Re-visualizes the road network if it is selected
            if self.selectedRoadNetwork:
                self.selectedRoadNetwork.visualize(self.roadGraphWidget)
            # Draw cross-hairs on graph
            if network is not None:
                self.selectedSocialNetwork = self.__socialNetworkObjs[network]
                self.ids, self.centers, sizes, relations, popSize = self.selectedSocialNetwork.getSummaryClusters(self.toolbar.clusterInput.textBox.text())
                self.visualizeSummaryData(self.ids, self.centers, sizes, relations, popSize)
                
        # Initialize community detector
        self.initializeCommunityDetector()

    # Creates network instances based on text data dictionary of {"NetworkName": {"Data":"Value", ...}
    # If the value is not set, square brackets denote that it is not set, written as "[Value]"
    @staticmethod
    def createNetworkInstances(data, type):
        instances = {}
        # Loops through all networks
        for network in data:
            kwargs = {}
            # Loops through all data in each network
            for dataKey in data[network]:
                dataValue = data[network][dataKey]
                # If the value is set, use it to create the instance
                if dataValue != f"[{dataKey}]":
                    kwargs[dataKey] = dataValue
            instances[network] = type(network, **kwargs)
        return instances

    # Links X and Y axis on main social network and road network graphs
    def linkGraphAxis(self):
        self.socialGraphWidget.setXLink(self.roadGraphWidget)
        self.socialGraphWidget.setYLink(self.roadGraphWidget)


    def __ViewStats(self):
        self.__windows[8] = QtWidgets.QWidget()
        self.__windows[8].setWindowModality(QtCore.Qt.ApplicationModal)
        self.__windows[8].setWindowTitle('Statistics')
        self.__windows[8].resize(int(self.frameGeometry().width() / 3), int(self.frameGeometry().height() / 3))
        
        StatsLayout = QtWidgets.QVBoxLayout(self)
        SummaryTimeLabel = QtWidgets.QLabel("Summary Response Time: " + str("{0:.3f}".format(self.SummaryResponseTime)) + " ms")
        StatsLayout.addWidget(SummaryTimeLabel)
        ClusterTimeLabel = QtWidgets.QLabel("Query Response Time: " + str("{0:.3f}".format(self.ClusterResponseTime)) + " ms")
        StatsLayout.addWidget(ClusterTimeLabel)
        StatsLayout.addStretch()
        
        self.__windows[8].setLayout(StatsLayout)
    

    
    def ShowStatsWindow(self):
        self.__windows[8].show()



    def closeEvent(self, a0: QtGui.QCloseEvent) -> None:
        print("Closed")
        exit(0)
        
    # Community search tree methods
    def pruneTree(self, tree):
        """
        Prune branches of the tree that don't have any satisfying users
        """
        # Base case: if tree is None or empty
        if not tree or not tree.get("children"):
            return tree
        
        # Process children
        for child_id in list(tree["children"].keys()):
            child = tree["children"][child_id]
            # Recursively prune the child
            pruned_child = self.pruneTree(child)
            
            # If child is None or has no satisfying users in its subtree, remove it
            if not pruned_child or (not pruned_child["satisfy"] and not any(c.get("satisfy", False) for c in pruned_child["children"].values())):
                del tree["children"][child_id]
            else:
                tree["children"][child_id] = pruned_child
        
        return tree

    def treeUsers(self, tree, result_users=None, pass_users=None):
        """Extract users from the tree, separating those that satisfy criteria from those that don't"""
        if result_users is None:
            result_users = []
        if pass_users is None:
            pass_users = []
            
        # Process current node
        if tree["satisfy"]:
            result_users.append(tree["user"])
        else:
            pass_users.append(tree["user"])
        
        # Process children recursively
        for child in tree["children"].values():
            self.treeUsers(child, result_users, pass_users)
            
        return result_users, pass_users

    def kdTree(self, queryKeywords, user, k, dThresh, e, dist, hops, visited):
        """Build a KD-truss tree for visualization"""
        if user in visited:
            return None
            
        visited.append(user)
        userKeywords = self.selectedSocialNetwork.getUserKeywords(user)
        
        # Calculate keyword similarity
        common = set(queryKeywords) & set(userKeywords)
        dSimilarity = len(common) / max(1, len(set(queryKeywords) | set(userKeywords)))
        
        # Check if this user satisfies all criteria
        satisfy = len(common) >= k and dist <= dThresh and hops <= e
        
        # Create node
        node = {
            "user": user,
            "keywords": list(userKeywords),
            "satisfy": satisfy,
            "distance": dist,
            "hops": hops,
            "children": {}
        }
        
        # Get user's relationships
        try:
            user_relations = self.selectedSocialNetwork.getUserRel(user)
            for rel in user_relations:
                if not rel:
                    continue
                    
                related_user = rel[0]
                if related_user not in visited and hops + 1 <= e:
                    # Calculate distance for this relationship
                    try:
                        loc1 = self.selectedSocialNetwork.userLoc(user)
                        loc2 = self.selectedSocialNetwork.userLoc(related_user)
                        
                        if loc1 and loc2:
                            new_dist = ((float(loc1[0][0]) - float(loc2[0][0]))**2 + 
                                      (float(loc1[0][1]) - float(loc2[0][1]))**2)**0.5
                            
                            # Only include if distance is within threshold
                            if new_dist <= dThresh:
                                child = self.kdTree(queryKeywords, related_user, k, dThresh, e, new_dist, hops + 1, visited)
                                if child:
                                    node["children"][related_user] = child
                    except:
                        pass
        except:
            pass
            
        return node
        
    def communityTree(self, user, queryKeywords, queryRels, k, r, minRel, d, e, visited, hop, deg_sim):
        """Build a community search tree for visualization"""
        if user in visited:
            return None
            
        visited.append(user)
        
        userKeywords = self.selectedSocialNetwork.getUserKeywords(user)
        
        # Calculate keyword similarity
        common = set(queryKeywords) & set(userKeywords) 
        if len(common) == 0 and len(queryKeywords) == 0:
            keyword_similarity = 0
        else:
            keyword_similarity = len(common) / max(1, len(set(queryKeywords) | set(userKeywords)))
        
        # Check if user is related to query user
        is_related = user in queryRels
        
        # Check if this user satisfies all criteria
        satisfy = len(common) >= k and (is_related or keyword_similarity >= e)
        
        # Create node
        node = {
            "user": user,
            "keywords": list(userKeywords),
            "satisfy": satisfy,
            "distance": deg_sim,
            "hops": hop,
            "deg_sim": keyword_similarity,
            "children": {}
        }
        
        # Explore neighbors if within radius
        if hop < r:
            try:
                user_relations = self.selectedSocialNetwork.getUserRel(user)
                for rel in user_relations:
                    if not rel:
                        continue
                        
                    related_user = rel[0]
                    if related_user not in visited:
                        # Only build subtree for users with minimum relation score
                        rel_score = 1.0  # Default relation score
                        
                        child = self.communityTree(
                            related_user, queryKeywords, queryRels, k, r, 
                            minRel, d, e, visited, hop + 1, keyword_similarity
                        )
                        if child:
                            node["children"][related_user] = child
            except:
                pass
                
        return node
        
    def communityTimeTree(self, user, queryKeywords, queryRels, queryPois, startDate, endDate, k, r, minRel, poi, d, e, visited, hop, deg_sim):
        """Build a time-based community search tree"""
        if user in visited:
            return None
            
        visited.append(user)
        
        userKeywords = self.selectedSocialNetwork.getUserKeywordsInTime(user, startDate, endDate)
        userPois = self.selectedSocialNetwork.getUserPoiInTime(user, startDate, endDate)
        
        # Calculate keyword similarity
        common = set(queryKeywords) & set(userKeywords) 
        if len(common) == 0 and len(queryKeywords) == 0:
            keyword_similarity = 0
        else:
            keyword_similarity = len(common) / max(1, len(set(queryKeywords) | set(userKeywords)))
        
        # Calculate POI similarity
        common_pois = set(queryPois) & set(userPois)
        poi_similarity = len(common_pois) / max(1, max(len(queryPois), len(userPois)))
        
        # Check if user is related to query user
        is_related = user in queryRels
        
        # Check if this user satisfies all criteria
        satisfy = (len(common) >= k and 
                  (is_related or keyword_similarity >= e) and 
                  poi_similarity >= poi)
        
        # Create node
        node = {
            "user": user,
            "keywords": list(userKeywords),
            "satisfy": satisfy,
            "distance": deg_sim,
            "hops": hop,
            "deg_sim": keyword_similarity,
            "children": {}
        }
        
        # Explore neighbors if within radius
        if hop < r:
            try:
                user_relations = self.selectedSocialNetwork.getUserRel(user)
                for rel in user_relations:
                    if not rel:
                        continue
                        
                    related_user = rel[0]
                    if related_user not in visited:
                        # Only build subtree for users with minimum relation score
                        rel_score = 1.0  # Default relation score
                        
                        child = self.communityTimeTree(
                            related_user, queryKeywords, queryRels, queryPois,
                            startDate, endDate, k, r, minRel, poi, d, e, 
                            visited, hop + 1, keyword_similarity
                        )
                        if child:
                            node["children"][related_user] = child
            except:
                pass
                
        return node