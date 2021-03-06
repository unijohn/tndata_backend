import axios from 'axios';
import React, { Component } from 'react';
import { debug } from './utils';

import Chat from './chat';

// If we're running over http, use ws://, if over https, use wss://
const PROTOCOLS = {
    'https:': 'wss://',
    'http:': 'ws://',
}

// Ensure our chat app hits the api running on the same host
// e.g. ==> ws://127.0.0.1:8000
let PORT = window.location.port;
if(PORT.length > 0) {
    PORT = ":8000";
}
const ROOT_URL = window.location.hostname + PORT;
const WS_HOST = PROTOCOLS[window.location.protocol] + ROOT_URL;
const API_HOST = window.location.protocol + '//' + ROOT_URL;


class App extends Component {

    constructor(props) {
        super(props)
        this.state = {
            user: {
                userId: '',
                email: '',
                username: 'Unknown',
                avatar: '',
                firstName: 'Unkown',
                lastName: 'User',
                token: this.props.apiToken
            },
            chatHistory: []
        }
        this.fetchMessageHistory = this.fetchMessageHistory.bind(this);
        this.fetchUser = this.fetchUser.bind(this);
        this.fetchProfile = this.fetchProfile.bind(this);
    }

    componentWillMount() {
        debug("== in componentWillMount()");
        this.fetchUser();
        this.fetchProfile();
    }

    fetchMessageHistory(currentUserId) {
        // NOTE: Called *after* we know the user's details
        const url = API_HOST + '/api/chat/history/?room=' + this.props.room;
        debug("Fetching history from " + url);
        axios.defaults.headers.common['Authorization'] = 'Token ' + this.props.apiToken;
        axios.get(url).then((resp) => {
            const data = resp.data;
            if(data.count > 0) {
                this.setState({user: this.state.user, chatHistory: data.results});
            }
            debug("Got " + data.count + " objects");
        });

        // Doing this means we're looking at the chat room, so just mark
        // all of it's messages as read.
        const readUrl = API_HOST + '/api/chat/read/';
        const payload = {'room': this.props.room }
        axios.put(readUrl, payload).then((resp) => {
            if(resp.status !== 204) {
                debug("FAIL | could not mark messages as read");
            } else {
                debug("Marked room messages as read.")
            }
        });


    }
    fetchUser() {
        const url = API_HOST + '/api/users/';
        axios.defaults.headers.common['Authorization'] = 'Token ' + this.props.apiToken;
        debug("Fetching User data from " + url + ", with token=" + this.props.apiToken);
        axios.get(url).then((resp) => {
            const data = resp.data;
            if(data.count === 1) {
                const userData = {
                    userId: data.results[0].id,
                    email: data.results[0].email,
                    username: data.results[0].username,
                    firstName: data.results[0].first_name,
                    lastName: data.results[0].last_name,
                    token: this.props.apiToken
                }
                debug("Got User Data: " + JSON.stringify(userData));
                this.setState({user: userData, chatHistory: this.state.chatHistory});
                this.fetchMessageHistory(data.results[0].id);
            } else {
                debug("FAIL | fetching user data: " + JSON.stringify(data));
            }
        });

    }

    fetchProfile() {
        const url = API_HOST + '/api/users/profile/';
        axios.defaults.headers.common['Authorization'] = 'Token ' + this.props.apiToken;
        debug("Fetching Profile from " + url + ", with token=" + this.props.apiToken);
        axios.get(url).then((resp) => {
            const data = resp.data;
            if(data.count === 1) {
                this.setState({
                    avatar: data.results[0].google_image
                });
                debug("Got Profile: " + JSON.stringify(data));
            } else {
                debug("FAIL | fetching profile: " + JSON.stringify(data));
            }
        });
    }

    render() {
        const path = window.location.pathname;
        const ws_url = WS_HOST + path +
            "?room=" + this.props.room +
            "&token=" + this.props.apiToken;
        debug("WS_URL = " + ws_url, true);
        return (
          <div>
            <Chat
                ws_url={ws_url}
                room={this.props.room}
                user={this.state.user}
                history={this.state.chatHistory} />
          </div>
        );
    }
}

export default App;
